import requests
import json
import sys

def test_firmware_check(base_url, device_model, device_version, wifi_version):
    """
    Test the firmware check endpoint by sending a POST request with device information.
    
    Args:
        base_url (str): The base URL of the firmware server
        device_model (str): The model number of the device
        device_version (str): The current device firmware version
        wifi_version (str): The current WiFi firmware version
    """
    # Construct the full URL
    url = f"{base_url}/firmware/check"
    
    # Prepare the request payload
    payload = {
        "device_model": device_model,
        "device_version": device_version,
        "wifi_version": wifi_version
    }
    
    # Set headers for JSON content
    headers = {
        "Content-Type": "application/json"
    }
    
    print(f"Sending request to {url}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        # Send the POST request
        response = requests.post(url, json=payload, headers=headers,verify=False)
        
        # Print the status code
        print(f"\nStatus Code: {response.status_code}")
        
        # Print the response headers
        print("\nResponse Headers:")
        for key, value in response.headers.items():
            print(f"{key}: {value}")
        
        # Print the response body
        print("\nResponse Body:")
        if response.status_code == 200:
            # Pretty print the JSON response
            response_json = response.json()
            print(json.dumps(response_json, indent=2))
            
            # Check if firmware updates are available
            if response_json.get("device", {}).get("upgradable"):
                print("\n✅ Device firmware update available!")
                print(f"Current version: {response_json['device']['current_version']}")
                print(f"Latest version: {response_json['device']['latest_version']}")
                print(f"Download URL: {response_json['device']['download_url']}")
            else:
                print("\n❌ No device firmware update available")
            
            if response_json.get("wifi", {}).get("upgradable"):
                print("\n✅ WiFi firmware update available!")
                print(f"Current version: {response_json['wifi']['current_version']}")
                print(f"Latest version: {response_json['wifi']['latest_version']}")
                print(f"Download URL: {response_json['wifi']['download_url']}")
            else:
                print("\n❌ No WiFi firmware update available")
        else:
            print(response.text)
    
    except requests.exceptions.RequestException as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    # Default values
    # default_base_url = "http://172.31.64.57:3000"
    default_base_url = "https://172.31.64.57:3443"
    default_device_model = "Z4000"
    default_device_version = "1.0.0"
    default_wifi_version = "1.0.0"
    
    # Get command line arguments or use defaults
    base_url = sys.argv[1] if len(sys.argv) > 1 else default_base_url
    device_model = sys.argv[2] if len(sys.argv) > 2 else default_device_model
    device_version = sys.argv[3] if len(sys.argv) > 3 else default_device_version
    wifi_version = sys.argv[4] if len(sys.argv) > 4 else default_wifi_version
    
    print("Firmware Check Test")
    print("==================")
    print(f"Server URL: {base_url}")
    print(f"Device Model: {device_model}")
    print(f"Device Version: {device_version}")
    print(f"WiFi Version: {wifi_version}")
    print("==================")
    
    # Run the test
    test_firmware_check(base_url, device_model, device_version, wifi_version) 