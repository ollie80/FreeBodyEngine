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
    def __init__(self, name: str):
        self._name = name

    def __getattr__(self, attr):
        def _missing_method(*args, **kwargs):
            if service_exists('logger'):
                warning(f"Attempted to use '{self._name}.{attr}', but the '{self._name}' service is not loaded.")
            return None
        return _missing_method

    def __repr__(self):
        return f"<MissingService '{self._name}'>"