import requests
from flask import Flask, jsonify, render_template
import urllib3
import json
from datetime import datetime, timedelta

# Suppress SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Prometheus server URL
PROMETHEUS_URL = "https://" # Change it accordingly
NAMESPACE = "" # Change it accordingly

app = Flask(__name__)

def fetch_data(query):
    """Fetch data from Prometheus, skipping SSL verification."""
    url = f"{PROMETHEUS_URL}/api/v1/query"
    params = {'query': query}
    try:
        response = requests.get(url, params=params, verify=False)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.RequestException as e:
        print(f"Error fetching data: {e}")
        return {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/metrics', methods=['GET'])
def get_metrics():
    queries = {
        "cpu_usage": f'sum(rate(container_cpu_usage_seconds_total{{namespace="{NAMESPACE}"}}[5m])) by (instance, pod)',
        "memory_usage": f'sum(container_memory_usage_bytes{{namespace="{NAMESPACE}"}}) by (instance, pod)',
        "disk_io": f'sum(rate(container_disk_io_total{{namespace="{NAMESPACE}"}}[5m])) by (instance, pod)',
        "network_traffic": f'sum(rate(container_network_transmit_bytes_total{{namespace="{NAMESPACE}"}}[5m])) by (instance, pod)'
    }

    metrics = {}
    for key, query in queries.items():
        data = fetch_data(query)
        parsed_data = parse_metric_data(data, key)
        for worker, pods in parsed_data.items():
            if worker not in metrics:
                metrics[worker] = {}
            for pod, values in pods.items():
                if pod not in metrics[worker]:
                    metrics[worker][pod] = {}
                metrics[worker][pod].update(values)

    # Convert metrics to human-readable format
    for worker, pods in metrics.items():
        for pod, values in pods.items():
            if 'cpu_usage' in values:
                metrics[worker][pod]['cpu_usage'] = format_cpu_usage(values['cpu_usage'])
            if 'memory_usage' in values:
                metrics[worker][pod]['memory_usage'] = bytes_to_human_readable(values['memory_usage'])
            if 'disk_io' in values:
                metrics[worker][pod]['disk_io'] = format_io(values['disk_io'])
            if 'network_traffic' in values:
                metrics[worker][pod]['network_traffic'] = bytes_to_human_readable(values['network_traffic'])

    return jsonify(metrics)

@app.route('/status', methods=['GET'])
def get_status():
    query = 'kube_pod_status_phase{namespace="%s"}' % NAMESPACE
    data = fetch_data(query)
    status = {}
    if 'data' in data and 'result' in data['data']:
        for item in data['data']['result']:
            pod = item['metric'].get('pod', 'unknown')
            phase = item['metric'].get('phase', 'unknown')
            status[pod] = phase
    return jsonify(status)

@app.route('/pods', methods=['GET'])
def get_pods():
    """Retrieve the list of pods."""
    query = f'kube_pod_info{{namespace="{NAMESPACE}"}}'
    data = fetch_data(query)
    pods = [item['metric'].get('pod', 'unknown') for item in data.get('data', {}).get('result', [])]
    return jsonify({'pods': pods})

@app.route('/network/<pod>', methods=['GET'])
def get_network_traffic(pod):
    """Retrieve network traffic data for a specific pod over the last 24 hours."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=1)
    query = f'sum(rate(container_network_transmit_bytes_total{{namespace="{NAMESPACE}", pod="{pod}"}}[5m])) by (instance, pod)'
    data = fetch_data(query)
    network_traffic = []

    if 'data' in data and 'result' in data['data']:
        for item in data['data']['result']:
            timestamp = item['value'][0]
            value = float(item['value'][1])
            network_traffic.append({
                'timestamp': timestamp,
                'value': value
            })

    return jsonify(network_traffic)

def parse_metric_data(data, key):
    """Parse the Prometheus metric data."""
    result = {}
    if 'data' in data and 'result' in data['data']:
        for item in data['data']['result']:
            worker = item['metric'].get('instance', 'unknown')
            pod = item['metric'].get('pod', 'unknown')
            value = item['value'][1]
            if worker not in result:
                result[worker] = {}
            if pod not in result[worker]:
                result[worker][pod] = {}
            result[worker][pod][key] = float(value)
    return result

def format_cpu_usage(value):
    """Format CPU usage."""
    return f"{value:.2f} cores"

def bytes_to_human_readable(value):
    """Convert bytes to a human-readable format."""
    value = float(value)
    if value < 1024:
        return f"{value:.2f} B"
    elif value < 1048576:
        return f"{value / 1024:.2f} KB"
    elif value < 1073741824:
        return f"{value / 1048576:.2f} MB"
    else:
        return f"{value / 1073741824:.2f} GB"

def format_io(value):
    """Format disk I/O."""
    return f"{value:.2f} I/O"

if __name__ == '__main__':
    app.run(debug=True)
