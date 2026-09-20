@tool
extends EditorPlugin
## File handoff and lifecycle only. Every terrain tool remains the upstream plugin.
const Archive = preload("project_archive.gd")
const Probe = preload("editor_probe.gd")
var _host: JavaScriptObject
var _dialog: FileDialog
var _ready_sent := false
var _busy := false
var _elapsed := 0.0

func _enter_tree() -> void:
	if OS.has_feature("web"):
		_configure_browser_editor()
	add_tool_menu_item("Export native project for Studio…", _choose_export)
	scene_changed.connect(_scene_changed)
	if OS.has_feature("web"):
		_host = JavaScriptBridge.get_interface("AxiomsFullEditor")
	else:
		_dialog = FileDialog.new()
		_dialog.access = FileDialog.ACCESS_FILESYSTEM
		_dialog.file_mode = FileDialog.FILE_MODE_SAVE_FILE
		_dialog.filters = PackedStringArray(["*.zip ; Complete native project"])
		_dialog.file_selected.connect(_export_project)
		add_child(_dialog)
	call_deferred("_select_terrain")

func _configure_browser_editor() -> void:
	var settings := EditorInterface.get_editor_settings()
	if not settings.has_setting("interface/editor/display_scale"):
		settings.set_setting("interface/editor/display_scale", 2)
	settings.set_setting("filesystem/import/use_multiple_threads", false)

func _exit_tree() -> void:
	remove_tool_menu_item("Export native project for Studio…")
	if scene_changed.is_connected(_scene_changed):
		scene_changed.disconnect(_scene_changed)

func _scene_changed(_root: Node) -> void:
	_ready_sent = false
	call_deferred("_select_terrain")

func _find_terrain(node: Node) -> Terrain3D:
	if node is Terrain3D:
		return node
	for child in node.get_children():
		var found := _find_terrain(child)
		if found != null:
			return found
	return null

func _select_terrain() -> void:
	var scene := EditorInterface.get_edited_scene_root()
	if scene == null:
		return
	var terrain := _find_terrain(scene)
	if terrain == null:
		return
	EditorInterface.set_main_screen_editor("3D")
	EditorInterface.get_selection().clear()
	EditorInterface.get_selection().add_node(terrain)
	EditorInterface.edit_node(terrain)

func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < 0.25:
		return
	_elapsed = 0.0
	if not _ready_sent:
		var state := inspect_editor()
		if state.get("ready", false):
			_ready_sent = true
			print("FULL_EDITOR_READY ", JSON.stringify(state))
			if _host != null:
				_host.report(JSON.stringify(state))
	if _host != null and not _busy:
		var request := String(_host.takeRequest())
		if request == "export-project":
			_export_project("user://terrain-project.zip")
		elif request in ["inspect", "inspect-controls"]:
			_host.report(JSON.stringify(inspect_editor(true, request == "inspect")))

func inspect_editor(detailed: bool = false, include_data: bool = true) -> Dictionary:
	var scene := EditorInterface.get_edited_scene_root()
	if scene == null:
		return {"ready": false, "reason": "No scene is open"}
	var terrain := _find_terrain(scene)
	if terrain == null:
		return {"ready": false, "reason": "Select a native Terrain3D scene"}
	var plugin := terrain.get_plugin()
	if plugin == null:
		return {"ready": false, "reason": "Upstream editor plugin is not active"}
	var ui: Node = plugin.get("ui")
	var dock: Control = plugin.get("asset_dock")
	var toolbar: Control = ui.get("toolbar") if ui != null else null
	var settings: Control = ui.get("tool_settings") if ui != null else null
	var state := {"ready": toolbar != null and settings != null and dock != null,
		"editor": "Godot Editor", "editor_version": Engine.get_version_info()["string"],
		"upstream_plugin": plugin.get_script().resource_path,
		"upstream_toolbar": toolbar.get_script().resource_path if toolbar != null else "",
		"upstream_settings": settings.get_script().resource_path if settings != null else "",
		"asset_dock": dock.get_script().resource_path if dock != null else "",
		"textures": terrain.assets.get_texture_count(), "mesh_assets": terrain.assets.get_mesh_count(),
		"regions": terrain.data.get_region_locations().size(), "scene": scene.scene_file_path}
	if detailed and state["ready"]:
		state["probe"] = Probe.inspect(terrain, include_data)
	return state

func _choose_export() -> void:
	if _host != null:
		_export_project("user://terrain-project.zip")
	else:
		_dialog.current_file = "terrain-project.zip"
		_dialog.popup_centered_ratio(0.65)

func _save_terrain_resources(node: Node) -> void:
	if node is Terrain3D:
		node.data.save_directory(node.data_directory)
		node.assets.save()
		node.material.save()
	for child in node.get_children():
		_save_terrain_resources(child)

func _export_project(path: String) -> void:
	if _busy:
		return
	_busy = true
	var scene := EditorInterface.get_edited_scene_root()
	if scene == null or scene.scene_file_path.is_empty():
		_failure("Save the current scene before exporting its native project.")
		return
	EditorInterface.save_all_scenes()
	_save_terrain_resources(scene)
	var metadata := {"format": "godot-native-project", "entry_scene": scene.scene_file_path}
	var viewport := EditorInterface.get_editor_viewport_3d(0)
	var image := viewport.get_texture().get_image()
	if image != null and not image.is_empty():
		var scale := minf(1.0, 1024.0 / float(image.get_width()))
		image.resize(maxi(1, roundi(image.get_width() * scale)), maxi(1, roundi(image.get_height() * scale)))
		if image.save_png("res://studio-preview.png") == OK:
			metadata["preview"] = "studio-preview.png"
	var descriptor := FileAccess.open("res://studio-project.json", FileAccess.WRITE)
	if descriptor == null:
		_failure("The native project entry could not be saved.")
		return
	descriptor.store_string(JSON.stringify(metadata, "\t") + "\n")
	descriptor.close()
	var result := Archive.write(path)
	if not result["ok"]:
		_failure(result["error"])
		return
	print("FULL_EDITOR_PROJECT_SAVED ", JSON.stringify({"files": result["files"].size(), "sha256": result["sha256"]}))
	if _host != null:
		_host.deliverProject(Marshalls.raw_to_base64(FileAccess.get_file_as_bytes(path)), JSON.stringify({"format": "godot-native-project", "sha256": result["sha256"], "file_count": result["files"].size(), "editor_state": inspect_editor(true)}))
	_busy = false

func _failure(message: String) -> void:
	_busy = false
	push_error(message)
	if _host != null:
		_host.report(JSON.stringify({"ready": _ready_sent, "error": message}))
