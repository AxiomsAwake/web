# Disabled optional diagnostic transfer

This compatibility action keeps the existing inputs and outputs available to callers while generic GitHub Actions artifact uploads are disabled. It returns an empty `artifact-id`, sets `outcome` to `disabled`, and reports that no staging copy was created. Callers must preserve originals through their own existing evidence path; the shim does not copy or delete caller files.

The retained `enabled`, `directory`, `patterns` and `name` inputs are accepted only for interface compatibility. No optional or automatic artifact transfer is available through this action. Test results remain in run logs and caller-owned local retention remains separate.
