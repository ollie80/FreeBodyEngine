from FreeBodyEngine import warning, service_exists

class ServiceLocator:
    """Tracks every registered `Service` by name - the backing store behind
    `FreeBodyEngine.register_service`/`get_service`/etc. Normally reached
    only through those module-level functions rather than used directly."""

    def __init__(self):
        """Starts with no services registered."""
        self.services: dict[str, Service] = {}

    def _register(self, service: 'Service'):
        dep = service._check_dependencies(self)

        if dep:
            self.services[service.name] = service
            service.on_initialize()
        else:
            warning(f'Dependencies not met on service "{service.name}"')


    def _get(self, name: str):
        return self.services.get(name, None)
    
    def _unregister(self, name: str):
        self.services.get(name).on_destroy()
        return self.services.pop(name, None)

    def _exists(self, name: str):
        return name in self.services


class Service:
    """Base class for engine services (registered with
    `FreeBodyEngine.register_service`). Subclasses declare `self.dependencies`
    (other service names that must already be registered before this one
    can be) and may override `on_initialize`/`on_destroy` for setup/teardown."""

    def __init__(self, name: str):
        """Names this service `name`, with no dependencies declared yet."""
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