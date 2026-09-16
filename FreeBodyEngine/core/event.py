from FreeBodyEngine.core.service import Service
from FreeBodyEngine import warning
from typing import Callable
import re

class Event:
    """A named, categorized event and the set of callbacks currently
    registered to run when it's emitted (see `EventManager`)."""

    def __init__(self, name: str, *categories: str):
        """Creates an event named `name` filed under `categories`, with no callbacks yet."""
        self.name = name
        self.callbacks: set[Callable] = set()
        self.categories: tuple[str] = categories
        self.values: tuple[any] = ()

    def __str__(self):
        return f"Event({self.name})"
        
    def __repr__(self):
        return str(self)

class EventManager(Service):
    """The engine's central pub/sub event bus (registered as the "event"
    service). An event must be registered (`register_event`), and optionally
    filed under one or more registered categories (`register_category`),
    before callbacks can be attached to it or it can be emitted."""

    def __init__(self):
        """Sets up empty event and category registries."""
        super().__init__('event')
        self.events: dict[str, Event] = {}
        self.categories = {}
        self.category_map: dict[str, list[str]] = {}

    def unregister_callback(self, event_name: str, callable: Callable):
            """Unregisters `callable` from `event_name`'s callbacks, warning
            instead if `event_name` isn't a registered event at all, or if
            `callable` isn't currently registered on it."""
            if event_name not in self.events:
                warning(f'Could not unregister callback "{callable.__name__}" from event "{event_name}" because that event is not registered.')
                return

            if callable not in self.events[event_name].callbacks:
                warning(f'Could not unregister callback "{callable.__name__}" from event "{event_name}" because it is not registered.')
                return

            self.events[event_name].callbacks.remove(callable)

    def query_events(self, query: str) -> list[Event]:
        """Parses `query` (whitespace-separated selector tokens) and returns
        the matching registered `Event` objects, deduplicated.

        Each token may combine:
        - `#name` - selects the event with this exact name.
        - `?substring` - selects every event whose name contains this substring.
        - `@category` - alongside a `#`/`?` selector, restricts those matches
          to events filed under this category (repeatable within a token).

        A token combining a `#name` selector with a `?substring` selector
        (or more than one of either) is invalid and only triggers a
        warning - nothing is added for it. A token that is only `@category`
        selector(s), with no `#`/`?` name selector, falls back to walking
        every registered category rather than filtering to the ones named
        in the token."""
        querys = query.split(' ')
        events = []

        for q in querys:
            event_querys = re.findall(r"#([^#@\?]+)", q)
            search = re.findall(r"\?([^#@\?]+)", q)
            categories = re.findall(r"@([^#@\?]+)", q)

            def add_event(events: list, event_name: str, event_obs):
                """Appends the event named `event_name` (looked up in `event_obs`) to `events` if it isn't already present, returning the (possibly unchanged) list - used to build query_events()'s result set without duplicates."""
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
        """Registers `callable` to run whenever `event_name` is emitted,
        warning instead if `event_name` isn't a registered event at all, or
        if `callable` is already registered on it."""
        if event_name not in self.events:
            warning(f'Could not register callback "{callable.__name__}" on event "{event_name}" because that event is not registered.')
            return

        if callable in self.events[event_name].callbacks:
            warning(f'Could not register callback "{callable.__name__}" on event "{event_name}" because it is already registered.')
            return

        self.events[event_name].callbacks.add(callable)

    def register_category(self, name: str, priority: int = 0):
        """Registers a new event category named `name` at `priority`,
        warning instead if it already exists."""
        if name in self.categories:
            warning(f'Could not register category "{name}" because it already exists.')
            return

        self.categories[name] = priority
        self.category_map[name] = []

    def register_event(self, name: str, *categorys: str):
        """Registers a new event named `name`, filed under `categorys` (each
        of which must already be a registered category - see
        `register_category`).

        Warns and aborts without ever creating the event if `name` is
        already taken, or if any of `categorys` isn't a registered category
        - in the latter case, any categories checked before the missing one
        will already have had `name` appended to their `category_map`
        entry, since the abort happens mid-loop."""
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
        """Unregisters the event named `name`, warning instead if it doesn't
        exist.

        Note: this reads `self.events[name].category`, but `Event` only
        defines a `categories` attribute - as written, this raises
        `AttributeError` whenever `name` does exist."""
        if name not in self.events:
            warning(f'Could not unregister event "{name}" because it does not exist')
            return

        for category in self.events[name].category:
            self.category_map[category].remove(name)

        del self.events[name]


    def emit(self, event: str, *callback_args, **callback_kwargs):
        """Invokes every callback registered on `event` with the given
        arguments, warning instead if `event` isn't registered."""
        if event not in self.events:
            warning(f'Event "{event}" is not registered.')
            return
        for callback in self.events[event].callbacks:
            callback(*callback_args, **callback_kwargs)