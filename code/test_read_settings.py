import requests

# get camera settings and status

url = "http://172.27.100.51:8080/gopro/camera/state"

response = requests.request("GET", url)

print(response.text)

# example invalid setting request

url = "http://172.27.100.51:8080/gopro/camera/setting"

querystring = {"option":"-1","setting":"2"}

response = requests.request("GET", url, params=querystring)

print(response.text)

# example get camera info for Serial Number

url = "http://172.27.100.51:8080/gopro/camera/info"

response = requests.request("GET", url)

print(response.text)