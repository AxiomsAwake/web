@tool
extends RefCounted
## Opaque native master, never reconstructed from a terrain preview.
const MAX_FILES := 12000
const MAX_BYTES := 512 * 1024 * 1024
const GENERATED := [".git", ".godot"]

static func write(destination: String) -> Dictionary:
	var project_root := ProjectSettings.globalize_path("res://").simplify_path().trim_suffix("/") + "/"
	if ProjectSettings.globalize_path(destination).simplify_path().begins_with(project_root):
		return {"ok": false, "error": "Write the archive outside its source project."}
	var inventory: Array[String] = []
	var gathered := _gather("res://", inventory)
	if not gathered["ok"]:
		return gathered
	inventory.sort()
	var manifest: Dictionary = {}
	var total := 0
	for source in inventory:
		var file := FileAccess.open(source, FileAccess.READ)
		if file == null:
			return {"ok": false, "error": "Cannot read " + source}
		total += file.get_length()
		if total > MAX_BYTES:
			return {"ok": false, "error": "Project exceeds the archive memory budget; use the native project directory directly."}
		manifest[source.trim_prefix("res://")] = {"bytes": file.get_length(), "sha256": FileAccess.get_sha256(source)}
		file.close()
	var temporary := destination + ".candidate"
	var zip := ZIPPacker.new()
	if zip.open(temporary) != OK:
		return {"ok": false, "error": "Cannot open the output archive."}
	for source in inventory:
		var relative := source.trim_prefix("res://")
		var bytes := FileAccess.get_file_as_bytes(source)
		if bytes.size() != manifest[relative]["bytes"] or _hash(bytes) != manifest[relative]["sha256"]:
			zip.close()
			DirAccess.remove_absolute(temporary)
			return {"ok": false, "error": "Project changed during export; save and retry."}
		if zip.start_file(relative) != OK or zip.write_file(bytes) != OK or zip.close_file() != OK:
			zip.close()
			DirAccess.remove_absolute(temporary)
			return {"ok": false, "error": "Archive write failed; previous export is unchanged."}
	if zip.close() != OK:
		DirAccess.remove_absolute(temporary)
		return {"ok": false, "error": "Archive could not be finalized."}
	var verify := ZIPReader.new()
	var opened := verify.open(temporary)
	if opened != OK:
		DirAccess.remove_absolute(temporary)
		return {"ok": false, "error": "Cannot reopen written archive: " + error_string(opened)}
	var index := verify_index(verify.get_files(), manifest)
	if not index["ok"]:
		verify.close()
		DirAccess.remove_absolute(temporary)
		return index
	for relative in manifest:
		var bytes := verify.read_file(relative)
		if bytes.size() != manifest[relative]["bytes"] or _hash(bytes) != manifest[relative]["sha256"]:
			verify.close()
			DirAccess.remove_absolute(temporary)
			return {"ok": false, "error": "Written source differs from saved project: " + relative}
	verify.close()
	var backup := destination + ".previous"
	if FileAccess.file_exists(destination):
		if FileAccess.file_exists(backup) and DirAccess.remove_absolute(backup) != OK:
			return {"ok": false, "error": "Cannot rotate the previous export."}
		if DirAccess.rename_absolute(destination, backup) != OK:
			return {"ok": false, "error": "Cannot preserve the previous export."}
	if DirAccess.rename_absolute(temporary, destination) != OK:
		if FileAccess.file_exists(backup):
			DirAccess.rename_absolute(backup, destination)
		return {"ok": false, "error": "Cannot promote the verified archive."}
	return {"ok": true, "path": destination, "files": manifest, "bytes": total, "sha256": FileAccess.get_sha256(destination)}

static func verify_index(entries: PackedStringArray, manifest: Dictionary) -> Dictionary:
	# Godot 4.7's ZIPPacker.start_file also writes parent-directory records.
	# Compare exact file membership, not the count of files PLUS directories.
	var allowed_directories: Dictionary = {}
	for path: String in manifest:
		var directory := path.get_base_dir()
		while not directory.is_empty():
			allowed_directories[directory + "/"] = true
			directory = directory.get_base_dir()
	var seen: Dictionary = {}
	var files := 0
	for entry in entries:
		if seen.has(entry):
			return {"ok": false, "error": "Duplicate written archive entry: " + entry}
		seen[entry] = true
		if entry.ends_with("/"):
			if not allowed_directories.has(entry):
				return {"ok": false, "error": "Unexpected archive directory: " + entry}
		elif not manifest.has(entry):
			return {"ok": false, "error": "Unexpected written file: " + entry}
		else:
			files += 1
	if files != manifest.size():
		return {"ok": false, "error": "Written archive is missing project files (%d of %d)." % [files, manifest.size()]}
	return {"ok": true}

static func _hash(bytes: PackedByteArray) -> String:
	var hash := HashingContext.new()
	hash.start(HashingContext.HASH_SHA256)
	# Empty native files are valid. Godot rejects update(empty), whereas
	# start followed by finish correctly produces the SHA-256 of zero bytes.
	if not bytes.is_empty():
		hash.update(bytes)
	return hash.finish().hex_encode()

static func _gather(directory: String, files: Array[String]) -> Dictionary:
	var dir := DirAccess.open(directory)
	if dir == null:
		return {"ok": false, "error": "Cannot read project directory."}
	# Native dependencies include .gdignore files. Preserve them byte-for-byte;
	# generated folders remain excluded and hidden secret files remain rejected.
	dir.include_hidden = true
	dir.include_navigational = false
	if dir.list_dir_begin() != OK:
		return {"ok": false, "error": "Cannot enumerate project directory: " + directory}
	var name := dir.get_next()
	while not name.is_empty():
		if name not in GENERATED:
			if dir.is_link(name):
				return {"ok": false, "error": "Resolve external/symlinked dependencies before project export: " + name}
			var path := directory.path_join(name)
			if dir.current_is_dir():
				var nested := _gather(path, files)
				if not nested["ok"]:
					return nested
			else:
				if name == ".env" or name.begins_with(".env."):
					return {"ok": false, "error": "Remove secret environment files from this authoring project before sharing."}
				files.append(path)
				if files.size() > MAX_FILES:
					return {"ok": false, "error": "Project exceeds the archive file-count budget; share its directory through Git."}
		name = dir.get_next()
	dir.list_dir_end()
	return {"ok": true}
