@tool
extends RefCounted
## Read-only UI observations; full native fingerprints only at data checkpoints.
const InstanceFingerprint = preload("instance_fingerprint.gd")

static func inspect(terrain: Terrain3D, include_data: bool = true) -> Dictionary:
	var started := Time.get_ticks_usec()
	var plugin := terrain.get_plugin()
	var ui: Node = plugin.get("ui")
	var toolbar: Control = ui.get("toolbar")
	var buttons: Array = []
	for child in toolbar.get_children():
		if child is Button and child.is_visible_in_tree():
			buttons.append({"name": child.name, "tooltip": child.tooltip_text,
				"rect": _rect(child.get_global_rect()), "pressed": child.button_pressed})
	var settings: Dictionary = {}
	var controls: Dictionary = ui.get("tool_settings").get("settings")
	for key in controls:
		var control: Variant = controls[key]
		if control is Range:
			settings[key] = {"value": control.value, "visible": control.is_visible_in_tree(),
				"minimum": control.min_value, "step": control.step,
				"rect": _rect(control.get_global_rect())}
	var focused := toolbar.get_viewport().gui_get_focus_owner()
	var focus: Dictionary = {} if focused == null else {"class": focused.get_class(), "name": str(focused.name)}
	var dock: Control = plugin.get("asset_dock")
	var assets: Array = []
	for kind in ["texture", "mesh"]:
		var list: Control = dock.get(kind + "_list")
		for index in range(list.get_child_count()):
			var entry: Control = list.get_child(index)
			if entry.is_visible_in_tree() and entry.get("resource") != null:
				assets.append({"kind": kind, "index": index, "selected": entry.get("is_selected"),
					"rect": _rect(entry.get_global_rect())})
	var regions: Array = []
	if include_data:
		var locations := terrain.data.get_region_locations()
		locations.sort_custom(func(a: Vector2i, b: Vector2i): return a.y < b.y or (a.y == b.y and a.x < b.x))
		for location in locations:
			var region := terrain.data.get_region(location)
			regions.append({"location": [location.x, location.y],
				"height": _hash(region.get_height_map().get_data()),
				"control": _hash(region.get_control_map().get_data()),
				"color": _hash(region.get_color_map().get_data()),
				"instances": InstanceFingerprint.digest(region.get_instances()),
				"instances_raw": _hash(var_to_bytes(region.get_instances())),
				"instance_count": _count_transforms(region.get_instances())})
	var viewport := EditorInterface.get_editor_viewport_3d(0)
	var camera := viewport.get_camera_3d()
	var host: Node = viewport.get_parent()
	while host != null and not host is Control:
		host = host.get_parent()
	var viewport_rect := Rect2(Vector2.ZERO, Vector2(viewport.size))
	if host is Control:
		viewport_rect = host.get_global_rect()
	var point := Vector3(0, terrain.data.get_height(Vector3.ZERO), 0)
	var pixel := camera.unproject_position(point) + viewport_rect.position
	return {"toolbar": buttons, "settings": settings, "assets": assets, "focus": focus,
		"active_tool": ui.get("active_tool"), "viewport": _rect(viewport_rect),
		"test_point": [pixel.x, pixel.y], "world_point": _vector(point),
		"camera_position": _vector(camera.global_position),
		"camera_forward": _vector(-camera.global_basis.z),
		"point_in_front": not camera.is_position_behind(point), "regions": regions,
		"includes_data": include_data, "probe_ms": (Time.get_ticks_usec() - started) / 1000.0}

static func _vector(value: Vector3) -> Array:
	return [value.x, value.y, value.z]

static func _rect(value: Rect2) -> Array:
	return [value.position.x, value.position.y, value.size.x, value.size.y]

static func _count_transforms(value: Variant) -> int:
	if value is Transform3D:
		return 1
	var count := 0
	if value is Dictionary:
		for child in value.values():
			count += _count_transforms(child)
	elif value is Array:
		for child in value:
			count += _count_transforms(child)
	return count

static func _hash(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(bytes)
	return hash.finish().hex_encode()
