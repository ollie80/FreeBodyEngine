import os
import json
import uuid
import tomllib

REGISTRY_DIR = os.path.join(os.path.expanduser("~"), "FreeBodyEngine")
REGISTRY_PATH = os.path.join(REGISTRY_DIR, "projects.json")

class ProjectRegistry:
    def __init__(self, registry_path=REGISTRY_PATH):
        self.registry_path = registry_path
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        self.projects = self._load()

    def _load(self):
        if os.path.exists(self.registry_path):
            with open(self.registry_path, "r") as f:
                projects = json.load(f)
                valid = []
                for project in projects:
                    if os.path.exists(project.get('path')):
                        valid.append(project)
                return valid
        return []

    def _save(self):
        with open(self.registry_path, "w") as f:
            json.dump(self.projects, f, indent=2)

    def _generate_id(self, name):
        used_ids = {int(p["id"]) for p in self.projects if p["id"].isdigit()}
        new_id = 0
        while new_id in used_ids:
            new_id += 1
        return str(new_id)
    
    def project_exists(self, id: int):
        for project in self.projects:
            if project.get('id') == id:
                return True
        return False

    def get_project_config(self, id: str):
        path = self.get_project_path(id) 
        config_path = os.path.join(path, 'fbproject.toml')
        txt = open(config_path).read()
        return tomllib.loads(txt)

    def add_project(self, path: str, name: str):
        path = os.path.abspath(path)
        if any(p['path'] == path for p in self.projects):
            return  # Already tracked
        proj_id = self._generate_id(name)
        self.projects.append({"id": proj_id, "name": name, "path": path})
        self._save()

    def remove_project_by_id(self, proj_id: str):
        self.projects = [p for p in self.projects if p["id"] != proj_id]
        self._save()

    def list_projects(self):
        return [f'{p.get('id')} - {p.get('name')}: "{p.get('path')}"' for p in self.projects]

    def get_project_name(self, id: str):
        for p in self.projects:
            if p.get('id') == id:
                
                return p.get('name')

    def get_project_path(self, id: int):
        for project in self.projects:
            if project.get('id') == id:
                return project.get("path")

    def get_project_id(self, name: str):
        for p in self.projects:
            if p["name"].lower() == name.lower():
                return p["id"]
        return None

    def get_project_by_id(self, proj_id: str):
        for p in self.projects:
            if p["id"] == proj_id:
                return p
        return None
