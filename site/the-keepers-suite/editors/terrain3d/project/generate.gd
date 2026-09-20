extends SceneTree
## One-time generic starter content. All subsequent editing/saving is upstream.
var failures := 0

func _initialize() -> void:
	call_deferred("_generate")

func _saved(resource: Resource, path: String) -> void:
	var error := ResourceSaver.save(resource, path, ResourceSaver.FLAG_CHANGE_PATH)
	if error != OK:
		push_error("Cannot save starter resource: " + path)
		failures += 1

func _generate() -> void:
	if FileAccess.file_exists("res://world.tscn"):
		push_error("Refusing to overwrite an existing native project")
		quit(1)
		return
	for directory in ["terrain", "assets"]:
		DirAccess.make_dir_recursive_absolute("res://" + directory)
	var world := Node3D.new()
	world.name = "World"
	root.add_child(world)
	var camera := Camera3D.new()
	camera.name = "PreviewCamera"
	world.add_child(camera)
	camera.owner = world
	camera.position = Vector3(150, 145, 155)
	camera.look_at(Vector3.ZERO)
	camera.far = 2000
	camera.current = true
	var terrain := Terrain3D.new()
	terrain.name = "Terrain"
	world.add_child(terrain)
	terrain.owner = world
	terrain.change_region_size(128)
	terrain.data_directory = "res://terrain"
	terrain.material.world_background = Terrain3DMaterial.NONE
	terrain.material.auto_shader = true
	terrain.material.set_shader_param("auto_base_texture", 0)
	terrain.material.set_shader_param("auto_overlay_texture", 1)
	terrain.material.set_shader_param("auto_slope", 1.0)
	terrain.assets = _assets()
	var height := Image.create(256, 256, false, Image.FORMAT_RF)
	var control := Image.create(256, 256, false, Image.FORMAT_RF)
	var color := Image.create(256, 256, false, Image.FORMAT_RGBA8)
	color.fill(Color.WHITE)
	var noise := FastNoiseLite.new()
	noise.seed = 721
	noise.frequency = 0.018
	noise.fractal_octaves = 4
	for z in range(256):
		for x in range(256):
			var h := noise.get_noise_2d(x, z) * 24.0
			height.set_pixel(x, z, Color(h, 0, 0, 1))
	terrain.data.import_images([height, control, color], Vector3(-128, 0, -128), 0.0, 1.0)
	for z in range(-128, 128):
		for x in range(-128, 128):
			terrain.data.set_control_auto(Vector3(x, 0, z), true)
	terrain.data.update_maps()
	var transforms: Array[Transform3D] = []
	for index in range(24):
		var point := Vector3(-35.0 + (index % 6) * 13.0, 0, -30.0 + floori(index / 6.0) * 15.0)
		point.y = terrain.data.get_height(point)
		transforms.append(Transform3D(Basis.IDENTITY.scaled(Vector3.ONE * (1.2 + index % 3)), point))
	terrain.instancer.add_transforms(0, transforms)
	terrain.data.save_directory("res://terrain")
	_saved(terrain.assets, "res://assets/terrain_assets.tres")
	_saved(terrain.material, "res://assets/terrain_material.tres")
	var environment := WorldEnvironment.new()
	environment.name = "Environment"
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.11, 0.15, 0.19)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color(0.72, 0.81, 0.91)
	environment.environment.ambient_light_energy = 0.45
	world.add_child(environment)
	environment.owner = world
	var sun := DirectionalLight3D.new()
	sun.name = "Sun"
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_energy = 1.05
	sun.shadow_enabled = true
	world.add_child(sun)
	sun.owner = world
	var scene := PackedScene.new()
	if scene.pack(world) != OK:
		failures += 1
	_saved(scene, "res://world.tscn")
	var entry := FileAccess.open("res://studio-project.json", FileAccess.WRITE)
	if entry == null:
		failures += 1
	else:
		entry.store_string(JSON.stringify({"format": "axioms.native-editor-project", "version": 1, "entry_scene": "res://world.tscn"}))
		entry.close()
	print("FULL_EDITOR_STARTER: textures=", terrain.assets.get_texture_count(), " meshes=", terrain.assets.get_mesh_count(), " regions=", terrain.data.get_region_locations().size(), " failures=", failures)
	world.free()
	quit(0 if failures == 0 else 1)

func _assets() -> Terrain3DAssets:
	var assets := Terrain3DAssets.new()
	var names := ["Meadow", "Rock", "Earth path"]
	var colors := [Color("63824a"), Color("85857e"), Color("997044")]
	for index in range(3):
		var image := Image.create(128, 128, false, Image.FORMAT_RGBA8)
		var normal := Image.create(128, 128, false, Image.FORMAT_RGBA8)
		normal.fill(Color(0.5, 0.5, 1.0, 0.85))
		var noise := FastNoiseLite.new()
		noise.seed = 1234 + index
		noise.frequency = 0.14
		for y in range(128):
			for x in range(128):
				var detail := noise.get_noise_2d(x, y)
				var albedo: Color = colors[index] * (0.85 + detail * 0.28)
				albedo.a = 0.5 + detail * 0.3
				image.set_pixel(x, y, albedo)
		image.generate_mipmaps()
		normal.generate_mipmaps()
		var texture := Terrain3DTextureAsset.new()
		texture.name = names[index]
		texture.albedo_texture = ImageTexture.create_from_image(image)
		texture.normal_texture = ImageTexture.create_from_image(normal)
		texture.uv_scale = 0.25
		_saved(texture.albedo_texture, "res://assets/surface_%d.res" % index)
		_saved(texture.normal_texture, "res://assets/normal_%d.res" % index)
		assets.set_texture(index, texture)
	var rock := MeshInstance3D.new()
	rock.name = "Rock_LOD0"
	var mesh := SphereMesh.new()
	mesh.radius = 1.2
	mesh.height = 1.4
	mesh.radial_segments = 12
	mesh.rings = 6
	var material := StandardMaterial3D.new()
	material.albedo_color = Color("727b69")
	material.roughness = 0.95
	mesh.material = material
	rock.mesh = mesh
	var scene := PackedScene.new()
	if scene.pack(rock) != OK:
		failures += 1
	_saved(scene, "res://assets/rock.tscn")
	rock.free()
	var mesh_asset := Terrain3DMeshAsset.new()
	mesh_asset.name = "Starter rock"
	mesh_asset.scene_file = scene
	assets.set_mesh_asset(0, mesh_asset)
	return assets
