from flask import Flask, render_template, request, Response
import ssl
import atexit
import yaml
from pyVim.connect import SmartConnect, Disconnect
from pyVmomi import vim
from datetime import datetime
import csv
from io import StringIO

app = Flask(__name__)
app.debug = False
app.config['TEMPLATES_AUTO_RELOAD'] = True

app.static_folder = 'static'




# Class definitions with parent references
class Vcenters:
    def __init__(self, vcenter_name, version_build=None, vcenter_site=None):
        self.vcenter_name = vcenter_name
        self.datacenters = {}
        self.clusters = {}
        self.hosts = {}
        self.version_build = version_build
        self.vcenter_site = vcenter_site

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

      # Initialize new memory attributes
        self.cluster_total_memory = 0
        self.cluster_memory_usage = 0
        self.cluster_free_memory = 0
        self.hosts = [] 

    def update_memory_stats(self, host_total_memory, host_memory_usage, host_free_memory):
        self.cluster_total_memory += host_total_memory
        self.cluster_memory_usage += host_memory_usage
        self.cluster_free_memory += host_free_memory

    @property
    def memory_usage_percentage(self):
        if self.cluster_total_memory > 0:
            return (self.cluster_memory_usage / self.cluster_total_memory) * 100
        else:
            return 0  # Return 0% if the total memory is zero to avoid division by zero        

    def __str__(self):
        return f"Cluster ID: {self.cluster_id}, Cluster Name: {self.cluster_name}, Parent Datacenter: {self.parent_datacenter.datacenter_name}, Total Memory: {self.cluster_total_memory} GB, Memory Usage: {self.cluster_memory_usage} GB, Free Memory: {self.cluster_free_memory} GB"
    
    def add_host(self, host_obj):
            self.hosts.append(host_obj)
            self.update_memory_stats(host_obj.host_total_memory, host_obj.host_memory_usage, host_obj.host_free_memory)

    @property       
    def hosts_names(self):
        return [host.host_name for host in self.hosts]    

class Hosts:
    def __init__(self, host_name, host_id, parent_cluster, host_ip, host_server_model, esx_version, esx_build, host_cpu, host_total_memory, serial_number, host_memory_usage, host_free_memory, connection_state, host_power_state, host_bios_version):
        self.host_name = host_name
        self.host_id = host_id
        self.parent_cluster = parent_cluster
        self.host_ip = host_ip
        self.host_server_model = host_server_model
        self.esx_version = esx_version
        self.esx_build = esx_build
        self.serial_number = serial_number
        self.host_cpu = host_cpu
        self.host_total_memory = host_total_memory
        self.host_memory_usage = host_memory_usage
        self.host_free_memory = host_free_memory
        self.connection_state = connection_state
        self.host_power_state = host_power_state
        self.host_bios_version = host_bios_version

    def __str__(self):
        return f"Host Name: {self.host_name}, Host ID: {self.host_id}, Parent Cluster: {self.parent_cluster.cluster_name}, IP: {self.host_ip}, Server Model: {self.host_server_model}, ESXi Version: {self.esx_version}, ESXi Build: {self.esx_build}, Host CPU: {self.host_cpu}, Host Memory: {self.host_total_memory}, Serial Number: {self.serial_number}"

# Dictionary to store Vcenter objects
vcenters_dict = {}

def print_topology(content, vcenter_name, vcenter_site):
    about_info = content.about
    vcenter_version_build = f"{about_info.version} build-{about_info.build}"
    vcenter_obj = Vcenters(vcenter_name, version_build=vcenter_version_build, vcenter_site=vcenter_site)
    vcenters_dict[vcenter_name] = vcenter_obj


    print(f"Processing vCenter: {vcenter_name}")

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
                        # host_ip = host.summary.managementServerIp

                        host_ip = None
                        for vnic in host.config.network.vnic:
                            if vnic.spec.ip.ipAddress:
                                host_ip = vnic.spec.ip.ipAddress
                                break  # Assuming the first IP is the management IP

                        
                        esx_version = host.config.product.fullName
                        esx_build = host.config.product.build

                        hardware_info = host.hardware.systemInfo
                        host_server_model = hardware_info.model
                        serial_number = hardware_info.serialNumber

                        host_cpu = host.hardware.cpuInfo.numCpuCores
                        host_summary = host.summary
                        host_total_memory = round(host_summary.hardware.memorySize / (1024 ** 3))
                        host_memory_usage = round (host.summary.quickStats.overallMemoryUsage / 1024)
                        host_free_memory = host_total_memory - host_memory_usage
                        connection_state = host.summary.runtime.connectionState
                        host_power_state = host.summary.runtime.powerState



                        bios_version_to_str = host.hardware.biosInfo.releaseDate

                        bios_version = str(bios_version_to_str)

                        # Convert the release date to a datetime object
                        date_time_obj = datetime.fromisoformat(bios_version)
                        # Format the date in the desired format (YYYY-MM-DD)
                        formatted_bios_release_date = date_time_obj.strftime("%Y-%m-%d")
                        # Now formatted_bios_release_date contains the date in the format YYYY-MM-DD
                        host_bios_version = formatted_bios_release_date


                        host_obj = Hosts(host_name, host_id, cluster_obj, host_ip, host_server_model, esx_version, esx_build, host_cpu, host_total_memory, serial_number, host_memory_usage, host_free_memory, connection_state, host_power_state, host_bios_version)
                        cluster_obj.add_host(host_obj) 
                        cluster_obj.update_memory_stats(host_total_memory, host_memory_usage, host_free_memory)
                        vcenter_obj.hosts[host_id] = host_obj

    print(f"Datacenters: {vcenter_obj.datacenters}")
    print(f"Clusters: {vcenter_obj.clusters}")
    print(f"Hosts: {vcenter_obj.hosts}")                        

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
    vcenter_site = vcenter['site']

    try:
        si = SmartConnect(host=vcenter_server, user=username, pwd=password, sslContext=context)
        atexit.register(Disconnect, si)

        content = si.RetrieveContent()
        # print_topology(content, vcenter_server)
        print_topology(content, vcenter_server, vcenter_site)
    except Exception as e:
        print(f"Failed to connect to {vcenter_server}: {e}")

# Function to print topology and search functionality remains the same
        

def search_all(criteria):
    results = []

    # Convert criteria to lowercase for case-insensitive comparison
    criteria_lower = criteria.lower()

    for vc_name, vcenter_obj in vcenters_dict.items():
        if criteria_lower in vc_name.lower():
            # Include 'vcenter_name' in the result for vCenter
            results.append({
                "type": "vCenter", 
                "display": f"vCenter: {vc_name}",
                "vcenter_name": vc_name  # Add this line
            })
        
        for dc_id, dc_obj in vcenter_obj.datacenters.items():
            if criteria_lower in dc_obj.datacenter_name.lower():
                results.append({"type": "Datacenter", "display": f"Datacenter: {dc_obj.datacenter_name}"})
            
            for cl_id, cl_obj in vcenter_obj.clusters.items():
                if criteria_lower in cl_obj.cluster_name.lower():
                    results.append({"type": "Cluster", "display": f"Cluster: {cl_obj.cluster_name}"})
                
                for host_id, host_obj in vcenter_obj.hosts.items():
                    if criteria_lower in host_obj.host_name.lower():
                        results.append({
                            "type": "Host",
                            "display": f"host: {host_obj.host_name}",
                            "vcenter_name": vc_name,  # This is already correctly set for host results
                            "host_id": host_id
                        })

    return results


        




@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        search_query = request.form['search']
        search_results = search_all(search_query)
        return render_template('index.html', search_results=search_results, vcenters_dict=vcenters_dict)

    return render_template('index.html', vcenters_dict=vcenters_dict)



@app.route('/hosts', methods=['GET'])
def hosts():
    # Define a list of all possible attribute keys
    default_attributes = ['host_name', 'host_server_model', 'esx_version', 'host_cpu', 'host_total_memory', 'serial_number', 'host_bios_version', 'host_free_memory']
    
    # Check if any attributes have been selected by the user; if not, use all default attributes
    selected_attributes = request.args.getlist('attributes') or default_attributes

    if 'submitted' in request.args and not selected_attributes:
        selected_attributes = []
    elif not selected_attributes:  # No form submission detected, display all by default
        selected_attributes = default_attributes

    # Check if the request is to export the hosts data
    if 'export' in request.args:
        si = StringIO()
        cw = csv.writer(si)
        # Write the header row based on selected attributes
        cw.writerow(selected_attributes)

        for vcenter_name, vcenter_obj in vcenters_dict.items():
            for host_id, host_obj in vcenter_obj.hosts.items():
                row = []
                for attr in selected_attributes:
                    value = getattr(host_obj, attr, '')  # Default to empty string if attribute not found
                    row.append(value)
                cw.writerow(row)

        output = si.getvalue()
        si.close()

        # Set up the response to download the file
        response = Response(output, mimetype='text/csv')
        response.headers['Content-Disposition'] = 'attachment; filename="hosts.csv"'
        return response

    # If not exporting, proceed to render the template
    all_hosts = []
    # Gather all hosts based on your data structure
    # This is a placeholder loop, adapt it to your actual data retrieval logic
    for vcenter_name, vcenter_obj in vcenters_dict.items():
        for host_id, host_obj in vcenter_obj.hosts.items():
            all_hosts.append((vcenter_name, host_obj))

    # Render the hosts template, passing both the hosts and the selected (or default) attributes
    return render_template('hosts.html', hosts=all_hosts, selected_attributes=selected_attributes)




@app.route('/vcenters')
def vcenters():
    print("Accessing /vcenters route")
    all_vcenters = list(vcenters_dict.values())
    return render_template('vcenters.html', vcenters=all_vcenters)


@app.route('/vcenter/<vcenter_name>')
def vcenter_topology(vcenter_name):
    if vcenter_name in vcenters_dict:
        vcenter_obj = vcenters_dict[vcenter_name]
        return render_template('vcenter_topology.html', vcenter_obj=vcenter_obj, vcenter_name=vcenter_name)
    else:
        return f"VCenter with name {vcenter_name} not found.", 404




@app.route('/host/<vcenter_name>/<host_id>')
def host_detail(vcenter_name, host_id):
    if vcenter_name in vcenters_dict:
        vcenter_obj = vcenters_dict[vcenter_name]
        if host_id in vcenter_obj.hosts:
            host_obj = vcenter_obj.hosts[host_id]
            return render_template('host_detail.html', host_obj=host_obj)


@app.route('/clusters')
def clusters():
    all_clusters = []
    # Iterate through each vCenter and its clusters
    for vcenter_name, vcenter_obj in vcenters_dict.items():
        for cluster_id, cluster_obj in vcenter_obj.clusters.items():
            all_clusters.append((vcenter_name, cluster_obj))

    # Render the clusters information in a template
    return render_template('clusters.html', clusters=all_clusters)

@app.route('/sites')
def sites():
    # Initialize an empty dictionary to hold sites and their associated vCenters
    sites_dict = {}

    # Iterate through the vcenters_dict to populate sites_dict
    for vcenter_name, vcenter_obj in vcenters_dict.items():
        site = vcenter_obj.vcenter_site
        if site in sites_dict:
            # Append the vCenter to the list of vCenters for this site
            sites_dict[site].append(vcenter_name)
        else:
            # Create a new entry in the dictionary for this site
            sites_dict[site] = [vcenter_name]

    # Render a template, passing the sites_dict
    return render_template('sites.html', sites_dict=sites_dict)


@app.route('/<vcenter_name>/cluster/<cluster_name>')
def cluster_detail(vcenter_name, cluster_name):
    # Check if the vCenter exists
    if vcenter_name in vcenters_dict:
        vcenter_obj = vcenters_dict[vcenter_name]
        # Iterate over clusters and find the one with the matching name
        for cluster_id, cluster_obj in vcenter_obj.clusters.items():
            if cluster_obj.cluster_name == cluster_name:
                # Render a template with the cluster's details
                return render_template('cluster_detail.html', cluster=cluster_obj, vcenter_name=vcenter_name)
        # If no cluster with the given name is found
        return f"Cluster with name '{cluster_name}' not found in vCenter {vcenter_name}.", 404
    else:
        return f"vCenter with name '{vcenter_name}' not found.", 404



if __name__ == "__main__":
    app.run(debug=False)

