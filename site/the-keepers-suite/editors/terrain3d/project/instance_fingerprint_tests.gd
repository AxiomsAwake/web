extends SceneTree
const Fingerprint = preload("res://addons/axioms_project_exchange/instance_fingerprint.gd")
var assertions := 0
var failures := 0

func _initialize() -> void:
	var source := {0: {Vector2i(1, 2): [[Transform3D.IDENTITY], PackedColorArray([Color(0.1, 0.2, 0.3, 1)]), true]}}
	var original := Fingerprint.digest(source)
	var changed := source.duplicate(true)
	changed[0][Vector2i(1, 2)][2] = false
	_check(Fingerprint.digest(changed) == original, "render dirty state is not authored data")
	_check(source[0][Vector2i(1, 2)][2] == true, "observation does not mutate the source")
	changed = source.duplicate(true)
	changed[0][Vector2i(1, 2)][0][0] = Transform3D(Basis.IDENTITY, Vector3(1, 2, 3))
	_check(Fingerprint.digest(changed) != original, "changed placement is detected")
	changed = source.duplicate(true)
	changed[0][Vector2i(1, 2)][0][0] = Transform3D(Basis(Vector3.UP, 0.5), Vector3.ZERO)
	_check(Fingerprint.digest(changed) != original, "changed rotation is detected")
	changed = source.duplicate(true)
	changed[0][Vector2i(1, 2)][0][0] = Transform3D(Basis.IDENTITY.scaled(Vector3(2, 1, 1)), Vector3.ZERO)
	_check(Fingerprint.digest(changed) != original, "changed scale is detected")
	changed = source.duplicate(true)
	changed[0][Vector2i(1, 2)][1][0] = Color(0.1, 0.2, 0.4, 1)
	_check(Fingerprint.digest(changed) != original, "changed color is detected")
	_check(Fingerprint.digest({1: source[0]}) != original, "changed mesh identity is detected")
	_check(Fingerprint.digest({0: {Vector2i(2, 2): source[0][Vector2i(1, 2)]}}) != original, "changed cell is detected")
	_check(Fingerprint.digest({}) != original, "missing placements are detected")
	var typed: Array[Transform3D] = [Transform3D.IDENTITY]
	changed = source.duplicate(true)
	changed[0][Vector2i(1, 2)][0] = typed
	_check(Fingerprint.digest(changed) == original, "equivalent container typing is stable")
	var ordered := {0: source[0], 1: source[0].duplicate(true)}
	var reordered := {1: source[0].duplicate(true), 0: source[0]}
	_check(Fingerprint.digest(ordered) == Fingerprint.digest(reordered), "dictionary insertion order is not authored data")
	print("FULL_EDITOR_INSTANCE_FINGERPRINT: %d assertions, %d failures" % [assertions, failures])
	quit(1 if failures else 0)

func _check(condition: bool, message: String) -> void:
	assertions += 1
	if not condition:
		failures += 1
		printerr("FAIL: " + message)
