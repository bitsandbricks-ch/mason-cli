# Repo settings in Mason

Every setting GitHub and GitLab let an API client read is on the repo page's **settings** panel (and, for GitHub,
`mason settings NAME`). This page lists them all, with what Mason does with each:

- **shown**: read and shown, by area. A row that can't be read says why (the plan, the repo's visibility, the
  token's scopes, or a feature that's off).
- **editable**: changed in place. Changes wait in a bar under the panel; *apply* sends them through the API.
- **`.mason.toml`**: *apply and keep* also writes the change into the repo's own `.mason.toml` (or
  `.mason/mason.toml`) under that key, so `mason doctor` holds the repo to it from then on. It is written like
  the branch rules panel writes: a pull request, or straight onto the default branch when the repo has
  `auto_push`.

From the command line:

```sh
mason settings web                 # every setting of acme/web, by area, with the lists
mason settings web actions --keys  # one area, with each setting's key
mason settings web has_wiki=off actions.allowed_actions=local_only retention.days=30
```

The settings come from `src/mason/catalog.py`; this page follows it.

## GitHub

### general

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| description | `description` | shown, editable | — |
| website | `homepage` | shown, editable | `homepage` |
| topics (keeping them means each must be there; others may stay) | `topics` | shown, editable | `topics` |
| visibility (doctor checks it, never changes it) | `visibility` | shown, editable | `visibility` |
| default branch (switches to a branch that exists; doctor's branch key renames it) | `default_branch` | shown, editable | — |
| template repository | `is_template` | shown, editable | `settings.is_template` |
| require sign-off on web commits | `web_commit_signoff_required` | shown, editable | `settings.web_commit_signoff_required` |
| archived (an archived repo is read-only) | `archived` | shown, editable | — |
| name | `name` | shown (renaming moves the repo: do it on GitHub) | — |

### features

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| issues | `has_issues` | shown, editable | `settings.has_issues` |
| projects | `has_projects` | shown, editable | `settings.has_projects` |
| wiki | `has_wiki` | shown, editable | `settings.has_wiki` |
| discussions | `has_discussions` | shown, editable | `settings.has_discussions` |
| allow forking (private repos of an org) | `allow_forking` | shown, editable | `settings.allow_forking` |

### pull requests

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| allow merge commits | `allow_merge_commit` | shown, editable | `settings.allow_merge_commit` |
| merge commit title | `merge_commit_title` | shown, editable | `settings.merge_commit_title` |
| merge commit message | `merge_commit_message` | shown, editable | `settings.merge_commit_message` |
| allow squash merging | `allow_squash_merge` | shown, editable | `settings.allow_squash_merge` |
| squash commit title | `squash_merge_commit_title` | shown, editable | `settings.squash_merge_commit_title` |
| squash commit message | `squash_merge_commit_message` | shown, editable | `settings.squash_merge_commit_message` |
| allow rebase merging | `allow_rebase_merge` | shown, editable | `settings.allow_rebase_merge` |
| allow auto-merge | `allow_auto_merge` | shown, editable | `settings.allow_auto_merge` |
| suggest updating PR branches | `allow_update_branch` | shown, editable | `settings.allow_update_branch` |
| delete head branches after merge | `delete_branch_on_merge` | shown, editable | `settings.delete_branch_on_merge` |

### security

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| GitHub Advanced Security | `sec.advanced_security` | shown, editable | `security.advanced_security` |
| GitHub Code Security | `sec.code_security` | shown, editable | `security.code_security` |
| secret scanning | `sec.secret_scanning` | shown, editable | `security.secret_scanning` |
| push protection | `sec.secret_scanning_push_protection` | shown, editable | `security.secret_scanning_push_protection` |
| non-provider patterns | `sec.secret_scanning_non_provider_patterns` | shown, editable | `security.secret_scanning_non_provider_patterns` |
| validity checks | `sec.secret_scanning_validity_checks` | shown, editable | `security.secret_scanning_validity_checks` |
| AI secret detection | `sec.secret_scanning_ai_detection` | shown, editable | — |
| Dependabot alerts | `alerts.enabled` | shown, editable | — |
| Dependabot security updates | `autofix.enabled` | shown, editable | `security.dependabot_security_updates` |
| private vulnerability reporting | `pvr.enabled` | shown, editable | `vulnerability_reporting` |
| CodeQL default setup | `codeql.state` | shown, editable | `code_scanning` |
| CodeQL query suite | `codeql.query_suite` | shown, editable | — |

### releases

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| immutable releases | `immutable.enabled` | shown, editable | `immutable_releases` |

### actions

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| Actions on | `actions.enabled` | shown, editable | `actions.enabled` |
| allowed actions | `actions.allowed_actions` | shown, editable | `actions.allowed_actions` |
| actions must be pinned to a full SHA | `actions.sha_pinning_required` | shown, editable | — |
| selected: GitHub's own actions (only counts with allowed actions = selected) | `selected.github_owned_allowed` | shown, editable | — |
| selected: verified creators | `selected.verified_allowed` | shown, editable | — |
| selected: these actions | `selected.patterns_allowed` | shown, editable | — |
| GITHUB_TOKEN default | `workflow.default_workflow_permissions` | shown, editable | `actions.default_workflow_permissions` |
| Actions may approve PRs | `workflow.can_approve_pull_request_reviews` | shown, editable | `actions.can_approve_pull_request_reviews` |
| workflows of other repos may use this one (private and internal repos) | `access.access_level` | shown, editable | — |
| artifact and log retention (days) | `retention.days` | shown, editable | `actions.retention_days` |
| approval for fork PRs | `forkapproval.approval_policy` | shown, editable | `actions.fork_pr_approval` |

### pages

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| Pages site (turning it on uses the build type below (workflow by default)) | `pages.on` | shown, editable | — |
| build | `pages.build_type` | shown, editable | `pages.build` |
| branch (legacy builds) | `pages.source_branch` | shown, editable | `pages.branch` |
| folder (legacy builds) | `pages.source_path` | shown, editable | `pages.path` |
| custom domain | `pages.cname` | shown, editable | `pages.cname` |
| enforce HTTPS | `pages.https_enforced` | shown, editable | `pages.https` |
| address | `pages.html_url` | shown (GitHub sets it) | — |

### moderation

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| interaction limit (a limit lasts as long as the expiry below) | `limits.limit` | shown, editable | — |
| limit expiry (used when you set a limit (one_week when unset)) | `limits.expiry` | shown, editable | — |

### about

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| fork | `fork` | shown | — |
| created | `created_at` | shown | — |
| last push | `pushed_at` | shown | — |
| language | `language` | shown | — |
| license | `license` | shown | — |
| size (KB) | `size` | shown | — |
| stars | `stargazers_count` | shown | — |
| forks | `forks_count` | shown | — |
| watchers | `subscribers_count` | shown | — |
| open issues and PRs | `open_issues_count` | shown | — |

### lists

| list | in Mason | `.mason.toml` |
|---|---|---|
| collaborators | shown, with a link to manage it | — |
| teams | shown, with a link to manage it | — |
| environments | shown, with a link to manage it | `environments` |
| Actions variables | shown, with a link to manage it | `variables` |
| Actions secrets (names) | shown, with a link to manage it; set values in the secrets panel | `secrets` |
| self-hosted runners | shown, with a link to manage it | — |
| webhooks | shown, with a link to manage it | `webhooks` |
| deploy keys | shown, with a link to manage it | `deploy_keys` |
| autolinks | shown, with a link to manage it | `autolinks` |
| custom properties | shown, with a link to manage it | `properties` |
| labels | shown, with a link to manage it | `labels` |
| rulesets | shown, with a link to manage it; edit them in the branch rules panel | — |


## GitLab

GitLab projects are read and changed in the web app (Mason reaches GitLab there). Settings marked Premium or
Ultimate show as read-only, with the reason, when the instance doesn't offer them.

### general

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| description | `description` | shown, editable | `gitlab.settings.description` |
| topics | `topics` | shown, editable | — |
| visibility | `visibility` | shown, editable | `gitlab.settings.visibility` |
| default branch | `default_branch` | shown, editable | `gitlab.settings.default_branch` |
| users can request access | `request_access_enabled` | shown, editable | `gitlab.settings.request_access_enabled` |
| email notifications | `emails_enabled` | shown, editable | `gitlab.settings.emails_enabled` |
| default emoji reactions | `show_default_award_emojis` | shown, editable | `gitlab.settings.show_default_award_emojis` |
| Git LFS | `lfs_enabled` | shown, editable | `gitlab.settings.lfs_enabled` |
| service desk | `service_desk_enabled` | shown, editable | `gitlab.settings.service_desk_enabled` |
| warn about unwanted characters | `warn_about_potentially_unwanted_characters` | shown, editable | `gitlab.settings.warn_about_potentially_unwanted_characters` |
| uploads need sign-in | `enforce_auth_checks_on_uploads` | shown, editable | `gitlab.settings.enforce_auth_checks_on_uploads` |
| archived (an archived project is read-only) | `archived` | shown, editable | — |
| name | `name` | shown (renaming moves the project: do it on GitLab) | — |

### features

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| issues | `issues_access_level` | shown, editable | `gitlab.settings.issues_access_level` |
| repository | `repository_access_level` | shown, editable | `gitlab.settings.repository_access_level` |
| merge requests | `merge_requests_access_level` | shown, editable | `gitlab.settings.merge_requests_access_level` |
| forks | `forking_access_level` | shown, editable | `gitlab.settings.forking_access_level` |
| CI/CD | `builds_access_level` | shown, editable | `gitlab.settings.builds_access_level` |
| wiki | `wiki_access_level` | shown, editable | `gitlab.settings.wiki_access_level` |
| snippets | `snippets_access_level` | shown, editable | `gitlab.settings.snippets_access_level` |
| pages | `pages_access_level` | shown, editable | `gitlab.settings.pages_access_level` |
| container registry | `container_registry_access_level` | shown, editable | `gitlab.settings.container_registry_access_level` |
| package registry | `packages_enabled` | shown, editable | `gitlab.settings.packages_enabled` |
| releases | `releases_access_level` | shown, editable | `gitlab.settings.releases_access_level` |
| environments | `environments_access_level` | shown, editable | `gitlab.settings.environments_access_level` |
| feature flags | `feature_flags_access_level` | shown, editable | `gitlab.settings.feature_flags_access_level` |
| infrastructure | `infrastructure_access_level` | shown, editable | `gitlab.settings.infrastructure_access_level` |
| monitor | `monitor_access_level` | shown, editable | `gitlab.settings.monitor_access_level` |
| analytics | `analytics_access_level` | shown, editable | `gitlab.settings.analytics_access_level` |
| security and compliance | `security_and_compliance_access_level` | shown, editable | `gitlab.settings.security_and_compliance_access_level` |
| requirements | `requirements_access_level` | shown, editable | `gitlab.settings.requirements_access_level` |
| model experiments | `model_experiments_access_level` | shown, editable | `gitlab.settings.model_experiments_access_level` |
| model registry | `model_registry_access_level` | shown, editable | `gitlab.settings.model_registry_access_level` |

### merge requests

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| merge method | `merge_method` | shown, editable | `gitlab.settings.merge_method` |
| squash commits | `squash_option` | shown, editable | `gitlab.settings.squash_option` |
| pipelines must succeed | `only_allow_merge_if_pipeline_succeeds` | shown, editable | `gitlab.settings.only_allow_merge_if_pipeline_succeeds` |
| skipped pipelines count as succeeded | `allow_merge_on_skipped_pipeline` | shown, editable | `gitlab.settings.allow_merge_on_skipped_pipeline` |
| all threads must be resolved | `only_allow_merge_if_all_discussions_are_resolved` | shown, editable | `gitlab.settings.only_allow_merge_if_all_discussions_are_resolved` |
| status checks must pass (GitLab Ultimate) | `only_allow_merge_if_all_status_checks_passed` | shown, editable | `gitlab.settings.only_allow_merge_if_all_status_checks_passed` |
| delete source branch by default | `remove_source_branch_after_merge` | shown, editable | `gitlab.settings.remove_source_branch_after_merge` |
| resolve outdated threads | `resolve_outdated_diff_discussions` | shown, editable | `gitlab.settings.resolve_outdated_diff_discussions` |
| print the MR link on push | `printing_merge_request_link_enabled` | shown, editable | `gitlab.settings.printing_merge_request_link_enabled` |
| close referenced issues | `autoclose_referenced_issues` | shown, editable | `gitlab.settings.autoclose_referenced_issues` |
| merged results pipelines (Premium) | `merge_pipelines_enabled` | shown, editable | `gitlab.settings.merge_pipelines_enabled` |
| merge trains (Premium) | `merge_trains_enabled` | shown, editable | `gitlab.settings.merge_trains_enabled` |
| allow skipping the train | `merge_trains_skip_train_allowed` | shown, editable | `gitlab.settings.merge_trains_skip_train_allowed` |
| forks target this project | `mr_default_target_self` | shown, editable | `gitlab.settings.mr_default_target_self` |
| merge commit template | `merge_commit_template` | shown, editable | `gitlab.settings.merge_commit_template` |
| squash commit template | `squash_commit_template` | shown, editable | `gitlab.settings.squash_commit_template` |
| suggestion commit message | `suggestion_commit_message` | shown, editable | `gitlab.settings.suggestion_commit_message` |
| MR description template | `merge_requests_template` | shown, editable | `gitlab.settings.merge_requests_template` |
| issue description template | `issues_template` | shown, editable | `gitlab.settings.issues_template` |
| issue branch name template | `issue_branch_template` | shown, editable | `gitlab.settings.issue_branch_template` |

### approvals

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| reset approvals on push | `approvals.reset_approvals_on_push` | shown, editable | — |
| MRs can't change approval rules | `approvals.disable_overriding_approvers_per_merge_request` | shown, editable | — |
| authors may approve their MRs | `approvals.merge_requests_author_approval` | shown, editable | — |
| committers can't approve | `approvals.merge_requests_disable_committers_approval` | shown, editable | — |
| approving asks for sign-in again | `approvals.require_reauthentication_to_approve` | shown, editable | — |
| reset only code owner approvals on push | `approvals.selective_code_owner_removals` | shown, editable | — |

### CI/CD

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| CI file | `ci_config_path` | shown, editable | `gitlab.settings.ci_config_path` |
| job timeout (seconds) | `build_timeout` | shown, editable | `gitlab.settings.build_timeout` |
| auto-cancel redundant pipelines | `auto_cancel_pending_pipelines` | shown, editable | `gitlab.settings.auto_cancel_pending_pipelines` |
| prevent outdated deployments | `ci_forward_deployment_enabled` | shown, editable | `gitlab.settings.ci_forward_deployment_enabled` |
| allow rollbacks | `ci_forward_deployment_rollback_allowed` | shown, editable | `gitlab.settings.ci_forward_deployment_rollback_allowed` |
| separate caches for protected branches | `ci_separated_caches` | shown, editable | `gitlab.settings.ci_separated_caches` |
| fork MRs run pipelines here | `ci_allow_fork_pipelines_to_run_in_parent_project` | shown, editable | `gitlab.settings.ci_allow_fork_pipelines_to_run_in_parent_project` |
| public pipelines | `public_jobs` | shown, editable | `gitlab.settings.public_jobs` |
| keep the latest artifacts | `keep_latest_artifact` | shown, editable | `gitlab.settings.keep_latest_artifact` |
| Auto DevOps | `auto_devops_enabled` | shown, editable | `gitlab.settings.auto_devops_enabled` |
| Auto DevOps deploys | `auto_devops_deploy_strategy` | shown, editable | `gitlab.settings.auto_devops_deploy_strategy` |
| instance runners | `shared_runners_enabled` | shown, editable | `gitlab.settings.shared_runners_enabled` |
| group runners | `group_runners_enabled` | shown, editable | `gitlab.settings.group_runners_enabled` |
| git strategy | `build_git_strategy` | shown, editable | `gitlab.settings.build_git_strategy` |
| git shallow clone depth | `ci_default_git_depth` | shown, editable | `gitlab.settings.ci_default_git_depth` |
| delete pipelines after (seconds) | `ci_delete_pipelines_in_seconds` | shown, editable | `gitlab.settings.ci_delete_pipelines_in_seconds` |
| who may cancel pipelines | `ci_restrict_pipeline_cancellation_role` | shown, editable | `gitlab.settings.ci_restrict_pipeline_cancellation_role` |
| restrict pipeline variables | `restrict_user_defined_variables` | shown, editable | `gitlab.settings.restrict_user_defined_variables` |
| who may set pipeline variables | `ci_pipeline_variables_minimum_override_role` | shown, editable | `gitlab.settings.ci_pipeline_variables_minimum_override_role` |
| job tokens may push | `ci_push_repository_for_job_token_allowed` | shown, editable | `gitlab.settings.ci_push_repository_for_job_token_allowed` |
| only listed projects use this project's job token | `jobtoken.inbound_enabled` | shown, editable | — |

### container cleanup

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| clean up images | `cleanup.enabled` | shown, editable | — |
| run every | `cleanup.cadence` | shown, editable | — |
| keep the newest | `cleanup.keep_n` | shown, editable | — |
| remove older than | `cleanup.older_than` | shown, editable | — |
| remove tags matching | `cleanup.name_regex` | shown, editable | — |
| keep tags matching | `cleanup.name_regex_keep` | shown, editable | — |

### push rules

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| tags can't be deleted | `push.deny_delete_tag` | shown, editable | — |
| authors must be members | `push.member_check` | shown, editable | — |
| reject secrets | `push.prevent_secrets` | shown, editable | — |
| reject unsigned commits | `push.reject_unsigned_commits` | shown, editable | — |
| reject commits without DCO | `push.reject_non_dco_commits` | shown, editable | — |
| committer must be a verified user | `push.commit_committer_check` | shown, editable | — |
| committer name must match the user | `push.commit_committer_name_check` | shown, editable | — |
| commit messages must match | `push.commit_message_regex` | shown, editable | — |
| commit messages must not match | `push.commit_message_negative_regex` | shown, editable | — |
| branch names must match | `push.branch_name_regex` | shown, editable | — |
| author emails must match | `push.author_email_regex` | shown, editable | — |
| file names that are refused | `push.file_name_regex` | shown, editable | — |
| largest file (MB, 0 = no limit) | `push.max_file_size` | shown, editable | — |

### about

| setting | key | in Mason | `.mason.toml` |
|---|---|---|---|
| created | `created_at` | shown | — |
| last activity | `last_activity_at` | shown | — |
| stars | `star_count` | shown | — |
| forks | `forks_count` | shown | — |
| open issues | `open_issues_count` | shown | — |
| empty | `empty_repo` | shown | — |

### lists

| list | in Mason | `.mason.toml` |
|---|---|---|
| members | shown, with a link to manage it | — |
| protected branches | shown, with a link to manage it | `gitlab.protected_branches` |
| protected tags | shown, with a link to manage it | — |
| webhooks | shown, with a link to manage it | — |
| deploy keys | shown, with a link to manage it | — |
| CI/CD variables (names) | shown, with a link to manage it | — |
| environments | shown, with a link to manage it | — |
| badges | shown, with a link to manage it | — |
| labels | shown, with a link to manage it | — |


## What neither API reaches

These are only on the website, so Mason links there instead:

- GitHub: the social preview image (doctor's `social_preview` only checks one is set), discussion categories
  (`discussions` only checks them), email notifications for pushes, and sponsorships (that's
  `.github/FUNDING.yml`, a file `mason sync` can share).
- GitHub: secrets' values are never readable; Mason shows their names and sets values in the secrets panel.
- GitLab: integrations (Slack, Jira, ...) and their tokens, mirroring credentials, and the values of masked
  CI/CD variables.
- Branch rulesets and protection have their own panel (branch rules) and `protect` key, so they're listed here
  only as a list.
