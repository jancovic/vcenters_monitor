from flask import Flask, render_template, request
import ssl
import atexit
import yaml
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim

app = Flask(__name__)

# Class definitions with parent references
class Vcenters:
    def __init__(self, vcenter_name):
        self.vcenter_name = vcenter_name
        self.datacenters = {}
        self.clusters = {}
        self.hosts = {}

class Datacenters:
    def __init__(self, datacenter_id, datacenter_name):
        self.datacenter_id = datacenter_id
        self.datacenter_name = datacenter_name

    def __str__(self):
        return f"Datacenter ID: {self.datacenter_id}, Datacenter Name: {self.datacenter_name}"

class Clusters:
    def __init__(self, cluster_id, cluster_name, parent_datacenter):
        self.cluster_id = cluster_id
        self.cluster_name = cluster_name
        self.parent_datacenter = parent_datacenter

    def __str__(self):
        return f"Cluster ID: {self.cluster_id}, Cluster Name: {self.cluster_name}, Parent Datacenter: {self.parent_datacenter.datacenter_name}"

class Hosts:
    def __init__(self, host_name, host_id, parent_cluster, host_ip, host_server_model, esx_version, esx_build, host_cpu, host_memory):
        self.host_name = host_name
        self.host_id = host_id
        self.parent_cluster = parent_cluster
        self.host_ip = host_ip
        self.host_server_model = host_server_model
        self.esx_version = esx_version
        self.esx_build = esx_build
        self.host_cpu = host_cpu
        self.host_memory = host_memory

    def __str__(self):
        return f"Host Name: {self.host_name}, Host ID: {self.host_id}, Parent Cluster: {self.parent_cluster.cluster_name}, IP: {self.host_ip}, Server Model: {self.host_server_model}, ESXi Version: {self.esx_version}, ESXi Build: {self.esx_build}, Host CPU: {self.host_cpu}, Host Memory: {self.host_memory}"

# Dictionary to store Vcenter objects
vcenters_dict = {}

def print_topology(content, vcenter_name):
    vcenter_obj = Vcenters(vcenter_name)
    vcenters_dict[vcenter_name] = vcenter_obj

    for datacenter in content.rootFolder.childEntity:
        if isinstance(datacenter, vim.Datacenter):
            datacenter_id = datacenter._moId
            datacenter_obj = Datacenters(datacenter_id, datacenter.name)
            vcenter_obj.datacenters[datacenter_id] = datacenter_obj

            for compute_resource in datacenter.hostFolder.childEntity:
                if isinstance(compute_resource, vim.ClusterComputeResource):
                    cluster_id = compute_resource._moId
                    cluster_name = compute_resource.name
                    cluster_obj = Clusters(cluster_id, cluster_name, datacenter_obj)
                    vcenter_obj.clusters[cluster_id] = cluster_obj

                    for host in compute_resource.host:
                        host_id = host._moId
                        host_name = host.name

                        # Fetch IP, server model, ESXi version, and build
                        host_ip = host.summary.managementServerIp
                        host_server_model = host.hardware.systemInfo.model
                        esx_version = host.config.product.fullName
                        esx_build = host.config.product.build
                        host_cpu = host.hardware.cpuInfo.numCpuCores
                        host_memory = round(host.hardware.memorySize / (1024 ** 3))
                        host_obj = Hosts(host_name, host_id, cluster_obj, host_ip, host_server_model, esx_version, esx_build, host_cpu, host_memory)
                        vcenter_obj.hosts[host_id] = host_obj

# Load vCenter credentials from a YAML file
with open("vcenters.yaml", 'r') as file:
    vcenters = yaml.safe_load(file)

# Disable SSL certificate verification
context = ssl._create_unverified_context()

# Connect to each vCenter and build the hierarchy
for vcenter in vcenters:
    vcenter_server = vcenter['vcenter_name']
    username = vcenter['login']
    password = vcenter['pass']

    try:
        si = SmartConnect(host=vcenter_server, user=username, pwd=password, sslContext=context)
        atexit.register(Disconnect, si)

        content = si.RetrieveContent()
        print_topology(content, vcenter_server)
    except Exception as e:
        print(f"Failed to connect to {vcenter_server}: {e}")

# Function to print topology and search functionality remains the same

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        search_query = request.form['search']
        search_results = search_all(search_query)
        return render_template('index.html', search_results=search_results, vcenters_dict=vcenters_dict)

    return render_template('index.html', vcenters_dict=vcenters_dict)

@app.route('/host/<vcenter_name>/<host_id>')
def host_detail(vcenter_name, host_id):
    if vcenter_name in vcenters_dict:
        vcenter_obj = vcenters_dict[vcenter_name]
        if host_id in vcenter_obj.hosts:
            host_obj = vcenter_obj.hosts[host_id]
            return render_template('host_detail.html', host_obj=host_obj)
    return "Host not found", 404



if __name__ == "__main__":
    app.run(debug=True)

