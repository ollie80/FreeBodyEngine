import socket
import time
import select
from enum import Enum, auto

RELIABLE_BIT = 1 << 0
ORDERED_BIT = 1 << 1

LOCAL = "127.0.0.1"

class PacketType(Enum):
    ACK =  auto()
    DATA = auto()

class Packet:
    def __init__(self, channel: int, type: PacketType):
        self.channel = channel
        self.type = type

class DataPacket(Packet):
    def __init__(self, channel: int, flags: int, seq: int, length: int, payload: any, address):
        super().__init__(channel, PacketType.DATA)
        self.channel = channel
        self.flags = flags
        self.seq = seq
        self.length = length
        self.payload = payload
        self.address = address

class ACKPacket(Packet):
    def __init__(self, channel: int, seq: int):
        super().__init__(channel, PacketType.ACK)
        self.channel = channel
        self.seq = seq

class SequenceHandler:
    def __init__(self, threshold=64):
        self.sequences = set()
        self.current_seq = -1
        self.threshold = threshold

    def is_duplicate(self, sequence):
        if sequence == self.current_seq:
            return True
        
        if sequence > self.current_seq:  
            self.current_seq = sequence
            for seq in self.sequences:
                if seq < self.current_seq - self.threshold:
                    self.sequences.remove(seq)
            return False

        if sequence < self.current_seq - self.threshold:
            return True

        if sequence in self.sequences:
            return True
        
        self.sequences.add(sequence)
        return False

class OrderedBuffer:
    def __init__(self):
        self.packets = {}
        self.next_seq = 0

    def check_packet(self, packet: DataPacket) -> list[DataPacket]:
        self.packets[packet.seq] = packet
        self.packets = dict(sorted(self.packets.items()))
        
        return self.get_releasable_packets()

    def get_releasable_packets(self):
        released = []
        while self.next_seq in self.packets:
            released.append(self.packets.pop(self.next_seq))
            self.next_seq = (self.next_seq + 1) & 0xFFFF  # wrap-around
        return released

NetworkAddress = tuple[str, int]    

class NetworkInterface:
    def __init__(self, port=7433, host=LOCAL, max_packet_size=4096, reliable_resend_threshold=0.3, sequence_duplicate_threshold=64):
        self.port = port
        self.host = host
        self.address = (self.host, self.port)

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind(self.address)
        self.socket.setblocking(False)
        self.packets: list[Packet] = []
        
        self.ordered_buffers: dict[NetworkAddress, OrderedBuffer] = {}

        self.max_packet_size = max_packet_size
        
        self.last_sequences: dict[NetworkAddress, SequenceHandler] = {}  
        self.sequence_duplicate_threshold = sequence_duplicate_threshold

        self.reliable_resend_threshold = reliable_resend_threshold

        self.seq_counter = 0
        self.pending_reliable = {}

    def is_packet_duplicate(self, seq: int, address):
        if address not in self.last_sequences:
            self.last_sequences[address] = SequenceHandler(self.sequence_duplicate_threshold)

        return self.last_sequences[address].is_duplicate(seq)

        
    def send_data_packet(self, channel: int, address, payload: bytes, reliable: bool = False, ordered: bool = False):
        seq = self.seq_counter & 0xFFFF
        self.seq_counter += 1

        flags = 0
        if reliable:
            flags |= RELIABLE_BIT
        if ordered:
            flags |= ORDERED_BIT

        header = PacketType.DATA.value.to_bytes(1, 'big') + channel.to_bytes(1, 'big') + flags.to_bytes(1, 'big') + seq.to_bytes(2, 'big') + len(payload).to_bytes(2, 'big')

        packet = header + payload
        self.send_packet(packet, address)

        if reliable:
            self.pending_reliable[seq] = (packet, time.time(), address)

        return seq

    def send_ack_packet(self, channel: int, address, seq: int):
        packet = PacketType.ACK.value.to_bytes(1, 'big') + channel.to_bytes(1, 'big') + seq.to_bytes(2, 'big')

        self.send_packet(packet, address)

    def send_packet(self, packet, address):
        try:
            self.socket.sendto(packet, address)
        except ConnectionResetError:
            # this is just windows being dumb, UDP doesnt have connections THATS THE WHOLE FUCKING POINT!!!! I HATE WINDOWS AHHHHHHHHHHH
            pass

    def recieve_packet(self):
        try:
            return self.socket.recvfrom(self.max_packet_size)
        except ConnectionResetError:
            return None, None

    def check_ordered_packet(self, packet: DataPacket, address: NetworkAddress):
        if address not in self.ordered_buffers:
            self.ordered_buffers[address] = OrderedBuffer()

        return self.ordered_buffers[address].check_packet(packet)

    def poll_data(self):
        while True:
            readable, _, _ = select.select([self.socket], [], [], 0)
            if not readable:
                break

            packet, address = self.recieve_packet()

            if packet == None:
                continue

            packet_type = packet[0]

            if packet_type == PacketType.DATA.value:
                data = packet[1:]

                channel_id = data[0]
                flags = data[1]
                seq = int.from_bytes(data[2:4], 'big')

                length = int.from_bytes(data[4:6], 'big')

                payload = data[6:6+length]
                
                reliable = (flags & RELIABLE_BIT) != 0
                ordered = (flags & ORDERED_BIT) != 0

                if self.is_packet_duplicate(seq, address):
                    if reliable:
                        self.send_ack_packet(channel_id, address, seq)
                    continue

                if reliable:
                    self.send_ack_packet(channel_id, address, seq)
                    
                pack = DataPacket(channel_id, flags, seq, length, payload, address)
                if not ordered:
                    self.packets.append(pack)
                else:
                    for p in self.check_ordered_packet(pack, address):
                        self.packets.append(p)

            elif packet_type == PacketType.ACK.value:
                data = packet[0:]
                    
                channel_id = data[0]
                seq = int.from_bytes(data[1:], 'big')
                del self.pending_reliable[seq]

                self.packets.append(ACKPacket(channel_id, seq))

    def process_reliable_packets(self):
        now = time.time()
        to_resend = []

        for seq, (packet, last_send_time, address) in list(self.pending_reliable.items()):
            if now - last_send_time > self.reliable_resend_threshold:
                to_resend.append((seq, packet, address))

        for seq, packet, address in to_resend:
            self.send_packet(packet, address)
            self.pending_reliable[seq] = (packet, now, address)

    def update(self):
        self.poll_data()
        self.process_reliable_packets()