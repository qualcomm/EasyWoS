# GitHub.com Setup Checklist

This document tracks the Qualcomm GitHub.com setup items for publishing `easywos-skills` under the `qualcomm` GitHub organization.

Checklist source:

<https://github.qualcomm.com/pages/osdo/handbook/qcom-github/docs/new-project-checklist/>

## Status

| Checklist item | Status | Notes |
| --- | --- | --- |
| Follow the New GitHub.com Contributor Step-by-Step Checklist to set up your GitHub.com account and join the GitHub.com Organization. | External action required | The repository maintainer must complete account setup and organization membership with the Qualcomm GitHub administrators. |
| Select a name for the open source project following the Repository Naming Guidelines. | Prepared | Proposed repository name: `easywos-skills`. Initial local assessment: the name is short, descriptive, uses dashes instead of underscores/spaces, does not start with a `Q` abbreviation, and does not include an obvious third-party or Qualcomm trademark. Formal repository-name/trademark approval is still required by the Qualcomm process unless an exception applies. |
| Create the repository with Internal visibility on `github.com/qualcomm`, for example `github.com/qualcomm/<your-project-name>`. | External action required | Target repository URL: `https://github.com/qualcomm/easywos-skills`. The current local remote is not yet under `github.com/qualcomm`; create, transfer, or move the repository under the `qualcomm` organization with Internal visibility before public release. |

## Local repository updates made for the target organization

The public-facing documentation has been updated to use the intended Qualcomm organization URL:

```text
https://github.com/qualcomm/easywos-skills.git
```

The `CODEOWNERS` file uses the intended organization namespace:

```text
@qualcomm/easywos-skills-maintainers
```

Replace this team with the actual approved maintainer team if Qualcomm GitHub administrators assign a different team name.

## Commands after the repository is created or moved

After `https://github.com/qualcomm/easywos-skills.git` exists and you have access, update the local remote:

```bash
git remote set-url origin https://github.com/qualcomm/easywos-skills.git
git remote -v
```

Then push the prepared branch:

```bash
git push -u origin main
```
