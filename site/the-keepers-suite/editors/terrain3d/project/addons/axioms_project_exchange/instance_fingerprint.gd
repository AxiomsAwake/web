@tool
extends RefCounted
## Read-only persistence oracle for Terrain3D 1.0.2's mesh/cell instance triples.
## Upstream _update_mmis resets triple[2] (render dirty flag), not authored data.
## Mesh identity, cell, every transform and every color remain exact and ordered.

static func digest(instances: Dictionary) -> String:
	var rows: Array = []
	var meshes := instances.keys()
	meshes.sort()
	for mesh in meshes:
		assert(mesh is int, "Unsupported Terrain3D mesh key")
		var cells: Dictionary = instances[mesh]
		var locations := cells.keys()
		locations.sort_custom(func(a: Vector2i, b: Vector2i): return a.y < b.y or (a.y == b.y and a.x < b.x))
		for location in locations:
			var triple: Array = cells[location]
			assert(triple.size() == 3 and triple[2] is bool, "Unsupported Terrain3D instance triple")
			assert(triple[0] is Array and triple[1] is PackedColorArray, "Unsupported Terrain3D placement payload")
			assert(triple[0].size() == triple[1].size(), "Terrain3D placements and colors differ in length")
			# Normalize container typing/order, never authored numbers or order.
			var transforms: Array = []
			for transform in triple[0]:
				assert(transform is Transform3D, "Unsupported Terrain3D placement")
				transforms.append(transform)
			rows.append([mesh, location, transforms, triple[1]])
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	hash.update(var_to_bytes(rows))
	return hash.finish().hex_encode()
