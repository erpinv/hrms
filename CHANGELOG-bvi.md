# BVI fork changelog (`v16-bvi`)

`v16-bvi` = `upstream/version-16-hotfix` + the commits below. Each entry names the
upstream PR that carries (or will carry) the same change so it can be dropped once
an upstream release contains it.

| Step | Commit | Change | Upstream |
|---|---|---|---|
| 1 | — | Employer Contribution Journal Entry from Payroll Entry (`liability_account` on Salary Component Account) | frappe/hrms#5271, back-ported in #5274 (already on `version-16-hotfix`) |
| 2 | `23a5037ae` | fix: Salary Register crashes on employer contribution rows | pending (forward-port to `develop`) |
| 3 | `5a29b33b2` | feat: Additional Salary of type Employer Contribution applied to the slip's employer table | pending (forward-port to `develop`) |
| 4 | `f95bdb981` | feat: validate component types per Salary Structure table; employer components need a liability account and drop employee-pay/tax flags | pending (forward-port to `develop`) |
| 5 | — | feat: Employer Contribution Register report; `employee_share_component` pairing on Salary Component | pending (forward-port to `develop`) |
