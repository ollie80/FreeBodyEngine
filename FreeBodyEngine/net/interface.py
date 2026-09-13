import socket
import time
import select
from enum import Enum, auto

RELIABLE_BIT = 1 << 0
ORDERED_BIT = 1 << 1

BYTE_ORDER = 'big'

LOCAL = "127.0.0.1"

class PacketType(Enum):
    """The two wire-level packet kinds this protocol sends: `DATA` payloads
    and the `ACK`s that confirm a `RELIABLE_BIT` packet arrived."""
    ACK =  auto()
    DATA = auto()

class Packet:
    """Base class for a decoded packet - just enough shared state (`channel`,
    `type`) for both `DataPacket` and `ACKPacket`."""

    def __init__(self, channel: int, type: PacketType):
        """Args:
            channel: The logical channel this packet was sent/received on.
            type: The packet's `PacketType`.
        """
        self.channel = channel
        self.type = type

class DataPacket(Packet):
    """A decoded `DATA` packet carrying an application payload."""

    def __init__(self, channel: int, flags: int, seq: int, length: int, payload: any, address):
        """Args:
            channel: The logical channel this packet was sent/received on.
            flags: Bitfield of `RELIABLE_BIT`/`ORDERED_BIT`.
            seq: This packet's sequence number.
            length: Length of `payload`, in bytes.
            payload: The raw application payload.
            address: The `(host, port)` this packet came from/is going to.
        """
        super().__init__(channel, PacketType.DATA)
        self.channel = channel
        self.flags = flags
        self.seq = seq
        self.length = length
        self.payload = payload
        self.address = address

class ACKPacket(Packet):
    """A decoded `ACK` packet, confirming a `DataPacket` with sequence `seq` was received."""

    def __init__(self, channel: int, seq: int):
        """Args:
            channel: The logical channel the acknowledged packet was sent on.
            seq: The sequence number being acknowledged.
        """
        super().__init__(channel, PacketType.ACK)
        self.channel = channel
        self.seq = seq

class SequenceHandler:
    """Per-peer duplicate detection over a sliding window of recent sequence
    numbers, so a resent reliable packet (the sender never got the ACK) isn't
    processed twice."""

    def __init__(self, threshold=64):
        """Args:
            threshold: How far behind the highest sequence number seen a
                sequence number can still be and be tracked/considered - both
                bounds the memory used and means anything older is just
                assumed to be a duplicate.
        """
        self.sequences = set()
        self.current_seq = -1
        self.threshold = threshold

    def is_duplicate(self, sequence):
        """Whether `sequence` has already been seen, recording it if not.

        A new highest sequence number is never a duplicate, and also prunes
        `sequences` of anything now older than `threshold` behind it. A
        sequence number older than `threshold` behind the current highest is
        always treated as a duplicate (it's outside the tracked window, so
        there's no way to tell) - otherwise it's a duplicate only if already
        in `sequences`.
        """
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
    """Per-peer reordering buffer for packets sent with `ORDERED_BIT`: holds
    packets that arrived out of order until the ones before them (by
    sequence number) show up, so `check_packet` releases them strictly in
    sequence."""

    def __init__(self):
        """Starts an empty buffer expecting sequence number 0 next."""
        self.packets = {}
        self.next_seq = 0

    def check_packet(self, packet: DataPacket) -> list[DataPacket]:
        """Buffers `packet` and returns every packet (including `packet`
        itself, if it was next) now releasable in sequence order."""
        self.packets[packet.seq] = packet
        self.packets = dict(sorted(self.packets.items()))

        return self.get_releasable_packets()

    def get_releasable_packets(self):
        """Pops and returns every buffered packet starting at `next_seq` that
        forms an unbroken run, advancing `next_seq` (wrapping at 16 bits) past them."""
        released = []
        while self.next_seq in self.packets:
            released.append(self.packets.pop(self.next_seq))
            self.next_seq = (self.next_seq + 1) & 0xFFFF  # wrap-around
        return released

NetworkAddress = tuple[str, int]    
"""Contains the host and port."""
class NetworkInterface:
    """A basic UDP networking interface that inmplements TCP features to allow for both speed and reliability"""
    def __init__(self, port=7433, host=LOCAL, max_packet_size=4096, reliable_resend_threshold=0.3, sequence_duplicate_threshold=64):
        """Binds a non-blocking UDP socket at `(host, port)`.

        Args:
            port: Local UDP port to bind.
            host: Local address to bind.
            max_packet_size: Max bytes read per incoming packet in `recieve_packet`.
            reliable_resend_threshold: Seconds to wait for an ACK before resending a reliable packet.
            sequence_duplicate_threshold: Sliding-window size passed to each
                peer's `SequenceHandler` - see `SequenceHandler.threshold`.
        """
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
        """Whether `seq` from `address` is a duplicate, creating a fresh
        `SequenceHandler` for `address` the first time it's seen."""
        if address not in self.last_sequences:
            self.last_sequences[address] = SequenceHandler(self.sequence_duplicate_threshold)

        return self.last_sequences[address].is_duplicate(seq)
        
    def send_data_packet(self, channel: int, address, payload: bytes, reliable: bool = False, ordered: bool = False):
        """Encodes and sends a `DATA` packet to `address`, assigning it the
        next sequence number.

        If `reliable` is set, the packet is also stashed in
        `pending_reliable` so `process_reliable_packets` will keep resending
        it until an `ACK` for its sequence number arrives.

        Returns:
            The sequence number assigned to this packet.
        """
        seq = self.seq_counter & 0xFFFF
        self.seq_counter += 1

        flags = 0
        if reliable:
            flags |= RELIABLE_BIT
        if ordered:
            flags |= ORDERED_BIT

        header = PacketType.DATA.value.to_bytes(1, BYTE_ORDER) + channel.to_bytes(1, BYTE_ORDER) + flags.to_bytes(1, BYTE_ORDER) + seq.to_bytes(2, BYTE_ORDER) + len(payload).to_bytes(2, BYTE_ORDER)

        packet = header + payload
        self.send_packet(packet, address)

        if reliable:
            self.pending_reliable[seq] = (packet, time.time(), address)

        return seq

    def send_ack_packet(self, channel: int, address, seq: int):
        """Encodes and sends an `ACK` packet for sequence number `seq` to `address`."""
        packet = PacketType.ACK.value.to_bytes(1, BYTE_ORDER) + channel.to_bytes(1, BYTE_ORDER) + seq.to_bytes(2, BYTE_ORDER)

        self.send_packet(packet, address)

    def send_packet(self, packet, address):
        """Sends an already-encoded raw `packet` to `address`, silently
        dropping it if the peer is unreachable (see the `ConnectionError`
        comment below - UDP has no real "connection" to fail, so this can
        only mean a previous packet bounced)."""
        try:
            self.socket.sendto(packet, address)

        except ConnectionError:
            # this is just the OS being dumb, UDP doesn't have connections THATS THE WHOLE FUCKING POINT!!!! I HATE IT AHHHHHHHHHHH
            #
            # A previous send to a port nobody's listening on anymore (the
            # other side closed/crashed/quit) triggers an ICMP port-
            # unreachable, which surfaces as a real exception on this
            # *stateless* socket's next send/recv - not consistently the
            # same one across platforms: Windows raises ConnectionResetError
            # (WSAECONNRESET), Linux raises ConnectionRefusedError
            # (ECONNREFUSED) for the exact same "nobody's there" condition.
            # Only catching ConnectionResetError left the Linux case
            # completely uncaught - the entire game crashing the instant a
            # chat peer's process went away. ConnectionError is the common
            # base of both (and BrokenPipeError/ConnectionAbortedError),
            # so catch that instead of guessing per-platform.
            pass

    def recieve_packet(self):
        """Reads one raw packet off the socket, returning `(data, address)`,
        or `(None, None)` if the peer is unreachable (see `send_packet`)."""
        try:
            return self.socket.recvfrom(self.max_packet_size)

        except ConnectionError:
            return None, None


    def check_ordered_packet(self, packet: DataPacket, address: NetworkAddress):
        """Runs `packet` through `address`'s `OrderedBuffer`, creating one if
        this is the first ordered packet seen from `address`."""
        if address not in self.ordered_buffers:
            self.ordered_buffers[address] = OrderedBuffer()

        return self.ordered_buffers[address].check_packet(packet)


    def poll_data(self):
        """Drains every packet currently waiting on the socket, decoding each
        one and appending it to `self.packets`.

        Duplicate reliable packets are still ACKed (the peer may not have
        gotten the first ACK) but not re-appended. Ordered packets are only
        appended once released in sequence by `check_ordered_packet`, so an
        early arrival can sit buffered rather than showing up in `self.packets`
        right away. A received `ACK` instead clears the matching entry from
        `pending_reliable` so it stops being resent.
        """
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
                seq = int.from_bytes(data[2:4], BYTE_ORDER)

                length = int.from_bytes(data[4:6], BYTE_ORDER)

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
                seq = int.from_bytes(data[1:], BYTE_ORDER)
                del self.pending_reliable[seq]

                self.packets.append(ACKPacket(channel_id, seq))


    def process_reliable_packets(self):
        """Resends any packet in `pending_reliable` that's been waiting longer
        than `reliable_resend_threshold` for its `ACK`."""
        now = time.time()
        to_resend = []

        for seq, (packet, last_send_time, address) in list(self.pending_reliable.items()):
            if now - last_send_time > self.reliable_resend_threshold:
                to_resend.append((seq, packet, address))

        for seq, packet, address in to_resend:
            self.send_packet(packet, address)
            self.pending_reliable[seq] = (packet, now, address)


    def update(self):
        """Per-frame pump: reads and decodes any waiting packets, then resends
        any reliable packets that timed out waiting for an ACK."""
        self.poll_data()
        self.process_reliable_packets()