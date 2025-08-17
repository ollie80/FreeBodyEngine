from FreeBodyEngine.core.service import Service
from FreeBodyEngine import warning
from typing import Callable
import re

class Event:
    def __init__(self, name: str, *categories: str):
        self.name = name
        self.callbacks: set[Callable] = set()
        self.categories: tuple[str] = categories
        self.values: tuple[any] = ()

    def __str__(self):
        return f"Event({self.name})"
        
    def __repr__(self):
        return str(self)

class EventManager(Service):
    def __init__(self):
        super().__init__('event')
        self.events: dict[str, Event] = {}
        self.categories = {}
        self.category_map: dict[str, list[str]] = {}

    def unregister_callback(self, event_name: str, callable: Callable):
            if callable not in self.events[event_name].callbacks:
                warning(f'Could not unregister callback "{callable.__name__}" from event "{event_name}" because it is not registered.')
                return

            self.events[event_name].callbacks.remove(callable)

    def query_events(self, query: str) -> list[Event]:
        querys = query.split(' ')
        events = []

        for q in querys:
            event_querys = re.findall(r"#([^#@\?]+)", q)
            search = re.findall(r"\?([^#@\?]+)", q)
            categories = re.findall(r"@([^#@\?]+)", q)

            def add_event(events: list, event_name: str, event_obs):
                n_events = events
                e = event_obs[event_name]
                if e not in events:
                    n_events.append(e)
                    return n_events
                return n_events

            if (len(event_querys) > 0 and len(search) > 0) or (len(event_querys) > 1 or len(search) > 1):
                warning(f'Could not parse "{q}", event querys can only contain one name selector.')

            if len(event_querys) > 0:
                name_selector = event_querys[0]
                for name in self.events:
                    if name == name_selector:
                        if len(categories) > 0:
                            for category in categories:
                                if category in self.events[name].categories:
                                    events = add_event(events, name, self.events, )
                                    
                        else:
                            events = add_event(events, name, self.events)

            elif len(search) > 0:
                search_selector = search[0]
                for name in self.events:
                    if search_selector in name:
                        if len(categories) > 0:
                            for category in categories:
                                if category in self.events[name].categories:
                                    events = add_event(events, name, self.events)
                        else:
                            events = add_event(events, name, self.events)
            
            elif len(categories) > 0:
                for category in self.categories:
                    for event in self.category_map[category]:
                        events = add_event(events, event, self.events)

        return events

    def register_callback(self, event_name: str, callable: Callable):
        if callable in self.events[event_name].callbacks:
            warning(f'Could not register callback "{callable.__name__}" on event "{event_name}" because it is already registered.')
            return

        self.events[event_name].callbacks.add(callable)

    def register_category(self, name: str, priority: int = 0):
        if name in self.categories:
            warning(f'Could not register category "{name}" because it already exists.')
            return

        self.categories[name] = priority
        self.category_map[name] = []

    def register_event(self, name: str, *categorys: str):
        if name in self.events:
            warning(f'Could not register event "{name}" because it already exists.')
            return
        
        for category in categorys:
            if category in self.categories:
                self.category_map[category].append(name)
            else:
                warning(f'Category "{category}" does not exist.')
                return

        self.events[name] = Event(name, *categorys)
        

    def unregister_event(self, name: str):
        if name not in self.events:
            warning(f'Could not unregister event "{name}" because it does not exist')
            return
        
        for category in self.events[name].category:
            self.category_map[category].remove(name)

        del self.events[name]


    def emit(self, event: str, *callback_args, **callback_kwargs):
        if event not in self.events:
            warning(f'Event "{event}" is not registered.')
            return
        for callback in self.events[event].callbacks:
            callback(*callback_args, **callback_kwargs)