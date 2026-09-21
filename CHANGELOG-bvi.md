# BVI fork changelog (`v16-bvi`)

`v16-bvi` = `upstream/version-16-hotfix` + the commits below. Each entry names the
upstream PR that carries (or will carry) the same change so it can be dropped once
an upstream release contains it.

| Step | Commit | Change | Upstream |
|---|---|---|---|
| 1 | — | Employer Contribution Journal Entry from Payroll Entry (`liability_account` on Salary Component Account) | frappe/hrms#5271, back-ported in #5274 (already on `version-16-hotfix`) |
| 2 | `23a5037ae` | fix: Salary Register crashes on employer contribution rows | pending (forward-port to `develop`) |
| 3 | — | feat: Additional Salary of type Employer Contribution applied to the slip's employer table | pending (forward-port to `develop`) |
