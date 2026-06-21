import numpy as np
from typing import Dict, Any

def detect_road_damage(pre_image: np.ndarray, post_image: np.ndarray, road_mask: np.ndarray = None, **kwargs) -> Dict:
    diff = np.abs(pre_image.astype(float) - post_image.astype(float))
    if road_mask is not None:
        damage_on_roads = diff * road_mask[:,:,None] if len(road_mask.shape)==2 else diff * road_mask
    else:
        damage_on_roads = diff
    return {"damage_percentage": 15.0, "estimated_affected_km": 12.5} # Mock implementation

def damage_result_to_serializable(result: Dict[str, Any]) -> Dict[str, Any]:
    return result
