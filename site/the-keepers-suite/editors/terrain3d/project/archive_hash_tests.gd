extends SceneTree
const Archive = preload("res://addons/axioms_project_exchange/project_archive.gd")

func _initialize() -> void:
	var failures := 0
	var cases := [
		[PackedByteArray(), "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"],
		["abc".to_utf8_buffer(), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"]
	]
	for entry in cases:
		if Archive._hash(entry[0]) != entry[1]:
			failures += 1
			printerr("FAIL: native archive SHA-256 for %d bytes" % entry[0].size())
	print("FULL_EDITOR_ARCHIVE_HASH: %d assertions, %d failures" % [cases.size(), failures])
	quit(1 if failures else 0)
