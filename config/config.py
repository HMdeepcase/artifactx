import json
from pathlib import Path

# Global configuration instance
_global_config = None

class BaseConfig:
    def __init__(self, path: str | Path = "config.json"):
        # Get the directory where config.py is located
        config_dir = Path(__file__).parent
        # Join with the config filename
        config_path = config_dir / path
        object.__setattr__(self, "_path", config_path)
        with self._path.open(encoding="utf-8") as f:
            object.__setattr__(self, "_data", json.load(f))   # 안전하게 저장

    # Read-only
    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError as e:
            raise AttributeError(name) from e
            
    def get_path(self, path_type):
        """
        Construct a path based on the case name and path type.
        
        Args:
            path_type: Type of path to construct (e.g., 'root_dir', 'nav_path')
            
        Returns:
            Constructed path as a string
        """
        paths = self._data.get("paths", {})
        case_name = self._data.get("case_name", "")
        
        if path_type == "root_dir":
            return f"{paths.get('base_dir', 'test/backup')}/{case_name}/{paths.get('root_dir', 'Export')}"
        elif path_type == "attached_artifact_dir":
            return f"{paths.get('base_dir', 'test/backup')}/{case_name}/{paths.get('attached_artifact_dir', 'Export/Attachments')}"
        elif path_type == "nav_path":
            return f"{paths.get('base_dir', 'test/backup')}/{paths.get('nav_path', 'nav_data')}/{case_name}.json"
        elif path_type == "ground_truth_path":
            return f"{paths.get('ground_truth_dir', 'ground_truth')}/{case_name}_answers.json"
        elif path_type == "knowledge_data_path":
            return "test/knowledge/axiom_artifact_info_flat.json"
        elif path_type == "log_dir":
            return paths.get("log_dir", "logs")
        else:
            # Return the direct path from config if it exists
            if path_type in self._data:
                return self._data[path_type]
            # Or from paths section
            elif path_type in paths:
                return paths[path_type]
            return None

    @property
    def data(self):
        """Return the complete config data"""
        return self._data

class MCPConfig:
    def __init__(self, path: str | Path = "mcp_servers.json"):
        # Get the directory where config.py is located
        config_dir = Path(__file__).parent
        # Join with the config filename
        config_path = config_dir / path
        object.__setattr__(self, "_path", config_path)
        with self._path.open(encoding="utf-8") as f:
            object.__setattr__(self, "_data", json.load(f))

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError as e:
            raise AttributeError(name) from e
            
    @property
    def data(self):
        """Return the complete config data"""
        return self._data

def set_global_config(config: BaseConfig):
    """Set the global configuration instance."""
    global _global_config
    _global_config = config

def get_global_config() -> BaseConfig:
    """Get the global configuration instance, or create default if none set."""
    global _global_config
    if _global_config is None:
        _global_config = BaseConfig()
    return _global_config