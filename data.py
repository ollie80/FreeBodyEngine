import engine
import heapq


class KeyLocker:
    def __init__(self):
        self.items: dict[str, int] = {}
        self.next_id = 0
        self.free_ids = []  # min-heap for recycled IDs
        
    def get_id(self):
        # If there are any recycled IDs available, use the smallest one.
        if self.free_ids:
            return heapq.heappop(self.free_ids)
        else:
            current_id = self.next_id
            self.next_id += 1
            return current_id

    def add(self, key: str) -> int:
        # Assign a new id if key is not present already.
        if key not in self.items.keys():
            id = self.get_id()
            self.items[key] = id
            return id

    def remove(self, key: str):
        # When removing, push the freed id onto the free_ids heap for reuse.
        if key in self.items:
            freed_id = self.items.pop(key)
            heapq.heappush(self.free_ids, freed_id)

    def get_value(self, key: str):
        val = self.items.get(key)

        return val
    
import heapq

class IndexKeyLocker:  # Stores array indices for easy retrieval with keys
    def __init__(self):
        self.items: dict[int, str] = {}  # Mapping from ID to key
        self.index_to_id: dict[int, int] = {}  # Mapping from index to ID
        self.next_id = 0
        self.free_ids = []  # Min-heap for recycled IDs

    def get_id(self):
        """Returns the next available ID, using recycled ones if available."""
        if self.free_ids:
            return heapq.heappop(self.free_ids)
        else:
            current_id = self.next_id
            self.next_id += 1
            return current_id

    def add(self) -> str:
        """Adds a new key and assigns it the next available index."""
        item_id = self.get_id()
        key = f"key_{item_id}"  # Generate a key based on the ID
        self.items[item_id] = key
        index = len(self.index_to_id)
        self.index_to_id[index] = item_id

        return key

    def remove(self, key: str) -> int:
        """Removes a key and shifts indices to maintain sequential order."""
        for index, item_id in list(self.index_to_id.items()):
            if self.items.get(item_id) == key:
                # Remove the key and associated index
                del self.items[item_id]
                del self.index_to_id[index]
                heapq.heappush(self.free_ids, item_id)  # Recycle the ID

                # Shift all indices down to maintain sequence
                new_index_to_id = {}
                for new_index, (old_index, old_id) in enumerate(sorted(self.index_to_id.items())):
                    new_index_to_id[new_index] = old_id  # Re-map indices
                
                self.index_to_id = new_index_to_id
                return index  # Return the removed index

        return -1  # Key not found

    def get_index(self, key: str) -> int | None:
        """Returns the index of a key, or None if it doesn't exist."""
        for index, item_id in self.index_to_id.items():
            if self.items[item_id] == key:
                return index
        return None

