from FreeBodyEngine import warning, service_exists

class ServiceLocator:
    def __init__(self):
        self.services: dict[str, Service] = {}

    def _register(self, service: 'Service'):
        dep = service._check_dependencies(self)

        if dep:
            self.services[service.name] = service
            service.on_initialize()
        else:
            warning(f'Dependencies not meant on service "{service.name}"')


    def _get(self, name: str):
        return self.services.get(name, None)
    
    def _unregister(self, name: str):
        self.services.get(name).on_destroy()
        return self.services.pop(name, None)

    def _exists(self, name: str):
        return name in self.services


class Service:
    def __init__(self, name: str):
        self.name = name
        self.dependencies = []
        
    def _check_dependencies(self, locator: ServiceLocator):
        dependencies_satisfied = True
        for dependency in self.dependencies:
            if not locator._exists(dependency):
                dependencies_satisfied = False
                break
        
        return dependencies_satisfied

    def on_initialize(self):
        "Called when a service is registered."
        pass

    def on_destroy(self):
        "Called when a service is unregistered."
        pass

class NullService:
    def __init__(self, name: str, attr_path: str = None):
        self._name = name
        self._attr_path = attr_path or name

    def __getattr__(self, attr):
        return NullService(self._name, f"{self._attr_path}.{attr}")

    def __getitem__(self, key):
        return NullService(self._name, f"{self._attr_path}[{repr(key)}]")

    def __call__(self, *args, **kwargs):
        if service_exists('logger'):
            warning(f"Attempted to call '{self._attr_path}()', but the '{self._name}' service is not loaded.")
        return NullService(self._name, self._attr_path)

    def __bool__(self):
        return False

    def __iter__(self):
        return iter([])

    def __str__(self):
        return f"<MissingService '{self._attr_path}'>"

    def __repr__(self):
        return self.__str__()

    def __eq__(self, other):
        return isinstance(other, NullService)

    def __ne__(self, other):
        return not isinstance(other, NullService)

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __len__(self):
        return 0

    def __contains__(self, item):
        return False

    def __add__(self, other): return self
    def __radd__(self, other): return self
    def __sub__(self, other): return self
    def __rsub__(self, other): return self
    def __mul__(self, other): return self
    def __rmul__(self, other): return self
    def __truediv__(self, other): return self
    def __rtruediv__(self, other): return self
    def __floordiv__(self, other): return self
    def __mod__(self, other): return self
    def __pow__(self, other): return self
    def __and__(self, other): return self
    def __or__(self, other): return self
    def __xor__(self, other): return self
    def __lt__(self, other): return False
    def __le__(self, other): return False
    def __gt__(self, other): return False
    def __ge__(self, other): return False
