# test_receive_UDP.py
import socket

PC_IP = "172.27.100.56"  # DESTINATION IP from Wireshark
PORT = 8554              # DESTINATION PORT from Wireshark

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((PC_IP, PORT))
print("Bound to:", sock.getsockname())

while True:
    data, addr = sock.recvfrom(4096)
    print("Received", len(data), "bytes from", addr)