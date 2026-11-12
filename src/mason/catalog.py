"""Every repo setting GitHub and GitLab let an API client read, in one place: `mason settings` and the repo
page's settings panel show them all, change the ones the API can write, and can keep a change in the repo's
own .mason.toml so `mason doctor` holds the repo to it.

A setting is read from one source (an endpoint), shown in an area, and has a kind (bool, choice, int, text,
list). `keep` names where .mason.toml holds it ("" when doctor has no key for it); `ro` says why it can only be
read. Lists (collaborators, webhooks, environments, ...) are shown with where to manage them.

What neither API reaches (GitHub's social preview image, discussion categories, email notifications; GitLab's
integrations' secrets) is listed in docs/settings.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mason import core

ACCESS = ("disabled", "private", "enabled")  # GitLab's feature access levels
FORK_POLICIES = ("first_time_contributors_new_to_github", "first_time_contributors", "all_external_contributors")
LIMITS = ("none", "existing_users", "contributors_only", "collaborators_only")
EXPIRY = ("one_day", "three_days", "one_week", "one_month", "six_months")
GL_LEVEL = {0: "no access", 5: "minimal", 10: "guest", 15: "planner", 20: "reporter", 30: "developer",
            40: "maintainer", 50: "owner", 60: "admin"}


@dataclass(frozen=True)
class Setting:
    key: str  # unique: the field for the main source, "<src>.<field>" for the others
    label: str
    kind: str = "bool"  # bool | choice | int | text | list
    choices: tuple = ()
    keep: str = ""  # its .mason.toml path, dotted ("" = doctor has no key for it)
    ro: str = ""  # why it can only be read ("" = the API writes it)
    note: str = ""

    @property
    def src(self) -> str:
        return self.key.split(".", 1)[0] if "." in self.key else "main"

    @property
    def field(self) -> str:
        return self.key.split(".", 1)[1] if "." in self.key else self.key


@dataclass(frozen=True)
class Listing:
    key: str
    label: str
    path: str  # the API list, under the repo
    manage: str  # the settings page that changes it (under the repo's web address)
    keep: str = ""
    note: str = ""


@dataclass
class Area:
    name: str
    settings: list[Setting] = field(default_factory=list)


def B(key, label, keep="", **kw):
    return Setting(key, label, "bool", keep=keep, **kw)


def C(key, label, choices, keep="", **kw):
    return Setting(key, label, "choice", tuple(choices), keep=keep, **kw)


def T(key, label, keep="", **kw):
    return Setting(key, label, "text", keep=keep, **kw)


def N(key, label, keep="", **kw):
    return Setting(key, label, "int", keep=keep, **kw)


def L(key, label, keep="", **kw):
    return Setting(key, label, "list", keep=keep, **kw)


def RO(key, label, kind="text"):
    return Setting(key, label, kind, ro="facts")


# ── GitHub ───────────────────────────────────────────────────────────────────

S = "settings."
SEC = "security."
GITHUB = [
    Area("general", [
        T("description", "description"),
        T("homepage", "website", keep="homepage"),
        L("topics", "topics", keep="topics", note="keeping them means each must be there; others may stay"),
        C("visibility", "visibility", ("public", "private", "internal"), keep="visibility",
          note="doctor checks it, never changes it"),
        T("default_branch", "default branch", note="switches to a branch that exists; doctor's branch key renames it"),
        B("is_template", "template repository", keep=S + "is_template"),
        B("web_commit_signoff_required", "require sign-off on web commits", keep=S + "web_commit_signoff_required"),
        B("archived", "archived", note="an archived repo is read-only"),
        T("name", "name", ro="renaming moves the repo: do it on GitHub"),
    ]),
    Area("features", [
        B("has_issues", "issues", keep=S + "has_issues"),
        B("has_projects", "projects", keep=S + "has_projects"),
        B("has_wiki", "wiki", keep=S + "has_wiki"),
        B("has_discussions", "discussions", keep=S + "has_discussions"),
        B("allow_forking", "allow forking", keep=S + "allow_forking", note="private repos of an org"),
    ]),
    Area("pull requests", [
        B("allow_merge_commit", "allow merge commits", keep=S + "allow_merge_commit"),
        C("merge_commit_title", "merge commit title", ("PR_TITLE", "MERGE_MESSAGE"), keep=S + "merge_commit_title"),
        C("merge_commit_message", "merge commit message", ("PR_BODY", "PR_TITLE", "BLANK"),
          keep=S + "merge_commit_message"),
        B("allow_squash_merge", "allow squash merging", keep=S + "allow_squash_merge"),
        C("squash_merge_commit_title", "squash commit title", ("PR_TITLE", "COMMIT_OR_PR_TITLE"),
          keep=S + "squash_merge_commit_title"),
        C("squash_merge_commit_message", "squash commit message", ("PR_BODY", "COMMIT_MESSAGES", "BLANK"),
          keep=S + "squash_merge_commit_message"),
        B("allow_rebase_merge", "allow rebase merging", keep=S + "allow_rebase_merge"),
        B("allow_auto_merge", "allow auto-merge", keep=S + "allow_auto_merge"),
        B("allow_update_branch", "suggest updating PR branches", keep=S + "allow_update_branch"),
        B("delete_branch_on_merge", "delete head branches after merge", keep=S + "delete_branch_on_merge"),
    ]),
    Area("security", [
        B("sec.advanced_security", "GitHub Advanced Security", keep=SEC + "advanced_security"),
        B("sec.code_security", "GitHub Code Security", keep=SEC + "code_security"),
        B("sec.secret_scanning", "secret scanning", keep=SEC + "secret_scanning"),
        B("sec.secret_scanning_push_protection", "push protection", keep=SEC + "secret_scanning_push_protection"),
        B("sec.secret_scanning_non_provider_patterns", "non-provider patterns",
          keep=SEC + "secret_scanning_non_provider_patterns"),
        B("sec.secret_scanning_validity_checks", "validity checks", keep=SEC + "secret_scanning_validity_checks"),
        B("sec.secret_scanning_ai_detection", "AI secret detection"),
        B("alerts.enabled", "Dependabot alerts"),
        B("autofix.enabled", "Dependabot security updates", keep=SEC + "dependabot_security_updates"),
        B("pvr.enabled", "private vulnerability reporting", keep="vulnerability_reporting"),
        B("codeql.state", "CodeQL default setup", keep="code_scanning"),
        C("codeql.query_suite", "CodeQL query suite", ("default", "extended")),
    ]),
    Area("releases", [
        B("immutable.enabled", "immutable releases", keep="immutable_releases"),
    ]),
    Area("actions", [
        B("actions.enabled", "Actions on", keep="actions.enabled"),
        C("actions.allowed_actions", "allowed actions", ("all", "local_only", "selected"),
          keep="actions.allowed_actions"),
        B("actions.sha_pinning_required", "actions must be pinned to a full SHA"),
        B("selected.github_owned_allowed", "selected: GitHub's own actions",
          note="only counts with allowed actions = selected"),
        B("selected.verified_allowed", "selected: verified creators"),
        L("selected.patterns_allowed", "selected: these actions"),
        C("workflow.default_workflow_permissions", "GITHUB_TOKEN default", ("read", "write"),
          keep="actions.default_workflow_permissions"),
        B("workflow.can_approve_pull_request_reviews", "Actions may approve PRs",
          keep="actions.can_approve_pull_request_reviews"),
        C("access.access_level", "workflows of other repos may use this one", ("none", "user", "organization"),
          note="private and internal repos"),
        N("retention.days", "artifact and log retention (days)", keep="actions.retention_days"),
        C("forkapproval.approval_policy", "approval for fork PRs", FORK_POLICIES, keep="actions.fork_pr_approval"),
    ]),
    Area("pages", [
        B("pages.on", "Pages site", note="turning it on uses the build type below (workflow by default)"),
        C("pages.build_type", "build", ("workflow", "legacy"), keep="pages.build"),
        T("pages.source_branch", "branch (legacy builds)", keep="pages.branch"),
        C("pages.source_path", "folder (legacy builds)", ("/", "/docs"), keep="pages.path"),
        T("pages.cname", "custom domain", keep="pages.cname"),
        B("pages.https_enforced", "enforce HTTPS", keep="pages.https"),
        T("pages.html_url", "address", ro="GitHub sets it"),
    ]),
    Area("moderation", [
        C("limits.limit", "interaction limit", LIMITS, note="a limit lasts as long as the expiry below"),
        C("limits.expiry", "limit expiry", EXPIRY, note="used when you set a limit (one_week when unset)"),
    ]),
    Area("about", [
        RO("fork", "fork", "bool"), RO("created_at", "created"), RO("pushed_at", "last push"),
        RO("language", "language"), RO("license", "license"), RO("size", "size (KB)", "int"),
        RO("stargazers_count", "stars", "int"), RO("forks_count", "forks", "int"),
        RO("subscribers_count", "watchers", "int"), RO("open_issues_count", "open issues and PRs", "int"),
    ]),
]
GITHUB_LISTS = [
    Listing("collaborators", "collaborators", "/collaborators?affiliation=direct", "settings/access"),
    Listing("teams", "teams", "/teams", "settings/access"),
    Listing("environments", "environments", "/environments", "settings/environments", keep="environments"),
    Listing("variables", "Actions variables", "/actions/variables", "settings/variables/actions", keep="variables"),
    Listing("secrets", "Actions secrets (names)", "/actions/secrets", "settings/secrets/actions", keep="secrets",
            note="set values in the secrets panel"),
    Listing("runners", "self-hosted runners", "/actions/runners", "settings/actions/runners"),
    Listing("hooks", "webhooks", "/hooks", "settings/hooks", keep="webhooks"),
    Listing("keys", "deploy keys", "/keys", "settings/keys", keep="deploy_keys"),
    Listing("autolinks", "autolinks", "/autolinks", "settings/key_links", keep="autolinks"),
    Listing("properties", "custom properties", "/properties/values", "settings", keep="properties"),
    Listing("labels", "labels", "/labels", "labels", keep="labels"),
    Listing("rulesets", "rulesets", "/rulesets?includes_parents=true", "settings/rules",
            note="edit them in the branch rules panel"),
]
SOURCES = {  # where each source is read, under /repos/{repo}
    "main": "", "sec": "", "actions": "/actions/permissions", "selected": "/actions/permissions/selected-actions",
    "workflow": "/actions/permissions/workflow", "access": "/actions/permissions/access",
    "retention": "/actions/permissions/artifact-and-log-retention",
    "forkapproval": "/actions/permissions/fork-pr-contributor-approval", "alerts": "/vulnerability-alerts",
    "autofix": "/automated-security-fixes", "pvr": "/private-vulnerability-reporting",
    "immutable": "/immutable-releases", "codeql": "/code-scanning/default-setup", "pages": "/pages",
    "limits": "/interaction-limits",
}


# ── GitLab ───────────────────────────────────────────────────────────────────

G = "gitlab.settings."


def GA(key, label, choices=ACCESS):
    return C(key, label, choices, keep=G + key)


def gB(key, label, **kw):  # a project setting doctor compares as [gitlab] settings
    return B(key, label, keep=G + key, **kw)


def gC(key, label, choices, **kw):
    return C(key, label, choices, keep=G + key, **kw)


def gT(key, label, **kw):
    return T(key, label, keep=G + key, **kw)


def gN(key, label, **kw):
    return N(key, label, keep=G + key, **kw)


GITLAB = [
    Area("general", [
        gT("description", "description"),
        L("topics", "topics"),
        gC("visibility", "visibility", ("private", "internal", "public")),
        gT("default_branch", "default branch"),
        gB("request_access_enabled", "users can request access"),
        gB("emails_enabled", "email notifications"),
        gB("show_default_award_emojis", "default emoji reactions"),
        gB("lfs_enabled", "Git LFS"),
        gB("service_desk_enabled", "service desk"),
        B("warn_about_potentially_unwanted_characters", "warn about unwanted characters",
          keep=G + "warn_about_potentially_unwanted_characters"),
        gB("enforce_auth_checks_on_uploads", "uploads need sign-in"),
        B("archived", "archived", note="an archived project is read-only"),
        T("name", "name", ro="renaming moves the project: do it on GitLab"),
    ]),
    Area("features", [
        GA("issues_access_level", "issues"),
        GA("repository_access_level", "repository"),
        GA("merge_requests_access_level", "merge requests"),
        GA("forking_access_level", "forks"),
        GA("builds_access_level", "CI/CD"),
        GA("wiki_access_level", "wiki"),
        GA("snippets_access_level", "snippets"),
        GA("pages_access_level", "pages", ("disabled", "private", "enabled", "public")),
        GA("container_registry_access_level", "container registry"),
        gB("packages_enabled", "package registry"),
        GA("releases_access_level", "releases"),
        GA("environments_access_level", "environments"),
        GA("feature_flags_access_level", "feature flags"),
        GA("infrastructure_access_level", "infrastructure"),
        GA("monitor_access_level", "monitor"),
        GA("analytics_access_level", "analytics"),
        GA("security_and_compliance_access_level", "security and compliance"),
        GA("requirements_access_level", "requirements"),
        GA("model_experiments_access_level", "model experiments"),
        GA("model_registry_access_level", "model registry"),
    ]),
    Area("merge requests", [
        gC("merge_method", "merge method", ("merge", "rebase_merge", "ff")),
        gC("squash_option", "squash commits", ("never", "always", "default_on", "default_off")),
        B("only_allow_merge_if_pipeline_succeeds", "pipelines must succeed",
          keep=G + "only_allow_merge_if_pipeline_succeeds"),
        B("allow_merge_on_skipped_pipeline", "skipped pipelines count as succeeded",
          keep=G + "allow_merge_on_skipped_pipeline"),
        B("only_allow_merge_if_all_discussions_are_resolved", "all threads must be resolved",
          keep=G + "only_allow_merge_if_all_discussions_are_resolved"),
        B("only_allow_merge_if_all_status_checks_passed", "status checks must pass",
          keep=G + "only_allow_merge_if_all_status_checks_passed", note="GitLab Ultimate"),
        B("remove_source_branch_after_merge", "delete source branch by default",
          keep=G + "remove_source_branch_after_merge"),
        gB("resolve_outdated_diff_discussions", "resolve outdated threads"),
        B("printing_merge_request_link_enabled", "print the MR link on push",
          keep=G + "printing_merge_request_link_enabled"),
        gB("autoclose_referenced_issues", "close referenced issues"),
        gB("merge_pipelines_enabled", "merged results pipelines", note="Premium"),
        gB("merge_trains_enabled", "merge trains", note="Premium"),
        gB("merge_trains_skip_train_allowed", "allow skipping the train"),
        gB("mr_default_target_self", "forks target this project"),
        gT("merge_commit_template", "merge commit template"),
        gT("squash_commit_template", "squash commit template"),
        gT("suggestion_commit_message", "suggestion commit message"),
        gT("merge_requests_template", "MR description template"),
        gT("issues_template", "issue description template"),
        gT("issue_branch_template", "issue branch name template"),
    ]),
    Area("approvals", [
        B("approvals.reset_approvals_on_push", "reset approvals on push"),
        B("approvals.disable_overriding_approvers_per_merge_request", "MRs can't change approval rules"),
        B("approvals.merge_requests_author_approval", "authors may approve their MRs"),
        B("approvals.merge_requests_disable_committers_approval", "committers can't approve"),
        B("approvals.require_reauthentication_to_approve", "approving asks for sign-in again"),
        B("approvals.selective_code_owner_removals", "reset only code owner approvals on push"),
    ]),
    Area("CI/CD", [
        gT("ci_config_path", "CI file"),
        gN("build_timeout", "job timeout (seconds)"),
        C("auto_cancel_pending_pipelines", "auto-cancel redundant pipelines", ("enabled", "disabled"),
          keep=G + "auto_cancel_pending_pipelines"),
        gB("ci_forward_deployment_enabled", "prevent outdated deployments"),
        gB("ci_forward_deployment_rollback_allowed", "allow rollbacks"),
        gB("ci_separated_caches", "separate caches for protected branches"),
        B("ci_allow_fork_pipelines_to_run_in_parent_project", "fork MRs run pipelines here",
          keep=G + "ci_allow_fork_pipelines_to_run_in_parent_project"),
        gB("public_jobs", "public pipelines"),
        gB("keep_latest_artifact", "keep the latest artifacts"),
        gB("auto_devops_enabled", "Auto DevOps"),
        C("auto_devops_deploy_strategy", "Auto DevOps deploys", ("continuous", "manual", "timed_incremental"),
          keep=G + "auto_devops_deploy_strategy"),
        gB("shared_runners_enabled", "instance runners"),
        gB("group_runners_enabled", "group runners"),
        gC("build_git_strategy", "git strategy", ("fetch", "clone")),
        gN("ci_default_git_depth", "git shallow clone depth"),
        gN("ci_delete_pipelines_in_seconds", "delete pipelines after (seconds)"),
        C("ci_restrict_pipeline_cancellation_role", "who may cancel pipelines", ("developer", "maintainer", "no_one"),
          keep=G + "ci_restrict_pipeline_cancellation_role"),
        gB("restrict_user_defined_variables", "restrict pipeline variables"),
        gC("ci_pipeline_variables_minimum_override_role", "who may set pipeline variables",
          ("no_one_allowed", "developer", "maintainer", "owner")),
        gB("ci_push_repository_for_job_token_allowed", "job tokens may push"),
        B("jobtoken.inbound_enabled", "only listed projects use this project's job token"),
    ]),
    Area("container cleanup", [
        B("cleanup.enabled", "clean up images"),
        C("cleanup.cadence", "run every", ("1d", "7d", "14d", "1month", "3month")),
        C("cleanup.keep_n", "keep the newest", ("1", "5", "10", "25", "50", "100")),
        C("cleanup.older_than", "remove older than", ("7d", "14d", "30d", "60d", "90d")),
        T("cleanup.name_regex", "remove tags matching"),
        T("cleanup.name_regex_keep", "keep tags matching"),
    ]),
    Area("push rules", [
        B("push.deny_delete_tag", "tags can't be deleted"),
        B("push.member_check", "authors must be members"),
        B("push.prevent_secrets", "reject secrets"),
        B("push.reject_unsigned_commits", "reject unsigned commits"),
        B("push.reject_non_dco_commits", "reject commits without DCO"),
        B("push.commit_committer_check", "committer must be a verified user"),
        B("push.commit_committer_name_check", "committer name must match the user"),
        T("push.commit_message_regex", "commit messages must match"),
        T("push.commit_message_negative_regex", "commit messages must not match"),
        T("push.branch_name_regex", "branch names must match"),
        T("push.author_email_regex", "author emails must match"),
        T("push.file_name_regex", "file names that are refused"),
        N("push.max_file_size", "largest file (MB, 0 = no limit)"),
    ]),
    Area("about", [
        RO("created_at", "created"), RO("last_activity_at", "last activity"),
        RO("star_count", "stars", "int"), RO("forks_count", "forks", "int"),
        RO("open_issues_count", "open issues", "int"), RO("empty_repo", "empty", "bool"),
    ]),
]
GITLAB_LISTS = [
    Listing("members", "members", "/members", "-/project_members"),
    Listing("protected_branches", "protected branches", "/protected_branches", "-/settings/repository",
            keep="gitlab.protected_branches"),
    Listing("protected_tags", "protected tags", "/protected_tags", "-/settings/repository"),
    Listing("hooks", "webhooks", "/hooks", "-/hooks"),
    Listing("deploy_keys", "deploy keys", "/deploy_keys", "-/settings/repository"),
    Listing("variables", "CI/CD variables (names)", "/variables", "-/settings/ci_cd"),
    Listing("environments", "environments", "/environments", "-/environments"),
    Listing("badges", "badges", "/badges", "edit"),
    Listing("labels", "labels", "/labels", "-/labels"),
]
GL_SOURCES = {"main": "", "approvals": "/approvals", "push": "/push_rule", "jobtoken": "/job_token_scope",
              "cleanup": ""}


def catalog(provider: str) -> list[Area]:
    return GITLAB if provider == "gitlab" else GITHUB


def find(provider: str, key: str) -> Setting | None:
    return next((s for a in catalog(provider) for s in a.settings if s.key == key), None)


def status_of(err: Exception) -> str:
    if getattr(err, "status", None):
        return str(err.status)
    m = re.search(r"HTTP (\d{3})", str(err))
    return m.group(1) if m else ""


def short_err(err: Exception) -> str:
    text = str(err).strip().splitlines()[-1] if str(err).strip() else type(err).__name__
    text = re.sub(r"^gh api .*?: ", "", text)
    return {"404": "not there, or the token can't see it", "403": "the token may not read it",
            "409": "not offered for this repo"}.get(status_of(err), text[:160])


# ── reading ──────────────────────────────────────────────────────────────────


def _github_value(s: Setting, raw: dict):
    src, fld = s.src, s.field
    data = raw.get(src)
    if src == "main":
        if fld == "license":
            return ((data or {}).get("license") or {}).get("spdx_id")
        return (data or {}).get(fld)
    if src == "sec":
        got = ((raw.get("main") or {}).get("security_and_analysis") or {}).get(fld)
        return None if got is None else got.get("status") == "enabled"
    if data is None:
        return None
    if src == "codeql" and fld == "state":
        return data.get("state") == "configured"
    if src == "pages":
        if fld == "on":
            return bool(data)
        if fld.startswith("source_"):
            return (data.get("source") or {}).get(fld[len("source_"):])
        return data.get(fld)
    if src == "limits":
        if fld == "limit":
            return data.get("limit") or "none"
        return None  # the expiry is only sent; GitHub answers expires_at
    return data.get(fld)


def read_github(repo: str) -> dict:
    """{"areas": [{"name", "rows": [...]}], "lists": [...], "url"} with every setting of a GitHub repo."""
    raw: dict = {}
    errors: dict[str, str] = {}

    def fetch(src: str):
        path = SOURCES[src]
        try:
            if src == "alerts":
                try:
                    core.api("GET", f"/repos/{repo}{path}")
                    return src, {"enabled": True}, ""
                except RuntimeError as err:
                    if "404" in str(err):
                        return src, {"enabled": False}, ""
                    raise
            if src == "pvr" or src == "immutable":
                try:
                    return src, core.api("GET", f"/repos/{repo}{path}") or {}, ""
                except RuntimeError as err:
                    if src == "immutable" and "404" in str(err):
                        return src, {"enabled": False}, ""
                    raise
            if src == "pages":
                try:
                    return src, core.api("GET", f"/repos/{repo}{path}") or {}, ""
                except RuntimeError as err:
                    if "404" in str(err):
                        return src, {}, ""  # Pages is off
                    raise
            return src, core.api("GET", f"/repos/{repo}{path}") or {}, ""
        except core.RateLimited:
            raise
        except RuntimeError as err:
            return src, None, short_err(err)

    main = fetch("main")
    if main[1] is None:
        raise RuntimeError(f"couldn't read {repo}: {main[2]}")
    raw["main"] = main[1]
    others = [s for s in SOURCES if s not in ("main", "sec")]
    if raw["main"].get("private") is False:
        others.remove("access")  # only private and internal repos have it
        errors["access"] = "public repos don't have it"
    for src, data, err in core.pmap(fetch, others, workers=6):
        raw[src] = data
        if err:
            errors[src] = err
    if (raw.get("actions") or {}).get("allowed_actions") != "selected" and "selected" in errors:
        errors["selected"] = "only with allowed actions = selected"
    url = raw["main"].get("html_url") or f"{core.WEB}/{repo}"
    areas = []
    for area in GITHUB:
        rows = []
        for s in area.settings:
            value = _github_value(s, raw)
            why = s.ro or errors.get(s.src, "")
            if s.src == "sec" and value is None and not why:
                why = "not offered for this repo (plan or visibility)"
            if s.src == "pages" and s.field in ("cname", "https_enforced", "source_branch", "source_path") \
                    and not (raw.get("pages") or {}) and not why:
                why = "Pages is off"
            rows.append(row(s, value, why))
        areas.append({"name": area.name, "rows": rows})
    return {"provider": "github", "url": url, "settings_url": f"{url}/settings", "areas": areas,
            "lists": lists_github(repo, url)}


def row(s: Setting, value, why: str) -> dict:
    return {"key": s.key, "label": s.label, "kind": s.kind, "choices": list(s.choices), "value": value,
            "edit": not why, "why": "" if s.ro == "facts" else why, "fact": s.ro == "facts", "keep": s.keep,
            "note": s.note}


def item_github(key: str, x: dict) -> dict:
    if key == "collaborators":
        return {"name": x.get("login", ""), "detail": x.get("role_name", "")}
    if key == "teams":
        return {"name": x.get("slug") or x.get("name", ""), "detail": x.get("permission", "")}
    if key == "environments":
        rules = [r.get("type", "").replace("_", " ") for r in x.get("protection_rules") or []]
        return {"name": x.get("name", ""), "detail": ", ".join(rules) or "no protection rules"}
    if key == "variables":
        return {"name": x.get("name", ""), "detail": str(x.get("value", ""))[:60]}
    if key == "secrets":
        when = x.get("updated_at")
        return {"name": x.get("name", ""), "detail": f"updated {core.ago(when)}" if when else ""}
    if key == "runners":
        return {"name": x.get("name", ""), "detail": x.get("status", "")}
    if key == "hooks":
        cfg = x.get("config") or {}
        events = ", ".join(x.get("events") or [])
        return {"name": cfg.get("url", ""), "detail": ("" if x.get("active", True) else "inactive · ") + events}
    if key == "keys":
        return {"name": x.get("title", ""), "detail": "read-only" if x.get("read_only", True) else "can write"}
    if key == "autolinks":
        return {"name": x.get("key_prefix", ""), "detail": x.get("url_template", "")}
    if key == "properties":
        return {"name": x.get("property_name", ""), "detail": core.compact(x.get("value"))}
    if key == "labels":
        return {"name": x.get("name", ""), "detail": f"#{x.get('color', '')}"}
    if key == "rulesets":
        src = x.get("source_type") or ""
        where = f" · from the {src.lower()}" if src and src != "Repository" else ""
        return {"name": x.get("name", ""), "detail": (x.get("enforcement") or "") + where}
    return {"name": str(x.get("name") or x.get("id") or ""), "detail": ""}


LIST_KEYS = {"environments": "environments", "variables": "variables", "secrets": "secrets", "runners": "runners"}


def lists_github(repo: str, url: str) -> list[dict]:
    def one(lst: Listing) -> dict:
        out = {"key": lst.key, "label": lst.label, "manage": f"{url}/{lst.manage}", "keep": lst.keep,
               "note": lst.note, "items": [], "error": ""}
        try:
            got = core.api_pages(f"/repos/{repo}{lst.path}", LIST_KEYS.get(lst.key))
            out["items"] = [item_github(lst.key, x) for x in got[:200] if isinstance(x, dict)]
        except core.RateLimited:
            raise
        except RuntimeError as err:
            out["error"] = short_err(err)
        return out

    return core.pmap(one, GITHUB_LISTS, workers=6)


def _gitlab_value(s: Setting, raw: dict):
    src, fld = s.src, s.field
    if src == "cleanup":
        got = ((raw.get("main") or {}).get("container_expiration_policy") or {}).get(fld)
        return str(got) if fld == "keep_n" and got is not None else got
    data = raw.get(src)
    if data is None:
        return None
    if src == "jobtoken" and fld == "inbound_enabled":
        return data.get("inbound_enabled")
    return data.get(fld)


def read_gitlab(gl, repo: str) -> dict:
    proj = gl.project(repo)
    raw: dict = {}
    errors: dict[str, str] = {}
    for src, path in GL_SOURCES.items():
        if src == "cleanup":
            continue
        try:
            raw[src] = gl.api("GET", proj + path + ("?license=true" if src == "main" else "")) or {}
        except core.RateLimited:
            raise
        except RuntimeError as err:
            if src == "main":
                raise RuntimeError(f"couldn't read {repo}: {short_err(err)}") from err
            raw[src] = None
            errors[src] = "needs GitLab Premium, or the token can't see it" if src in ("push", "approvals") \
                and status_of(err) == "404" else short_err(err)
    url = raw["main"].get("web_url") or ""
    areas = []
    for area in GITLAB:
        rows = []
        for s in area.settings:
            value = _gitlab_value(s, raw)
            why = s.ro or errors.get(s.src, "")
            if s.src == "main" and s.field not in raw["main"] and s.ro != "facts" and not why:
                why = "not offered by this GitLab (version or plan)"
            if s.src == "cleanup" and raw["main"].get("container_expiration_policy") is None and not why:
                why = "the container registry is off"
            rows.append(row(s, value, why))
        areas.append({"name": area.name, "rows": rows})
    return {"provider": "gitlab", "url": url, "settings_url": f"{url}/edit" if url else "", "areas": areas,
            "lists": lists_gitlab(gl, repo, url)}


def item_gitlab(key: str, x: dict) -> dict:
    def levels(name):
        return ", ".join(GL_LEVEL.get(a.get("access_level"), str(a.get("access_level")))
                         for a in x.get(name) or []) or "nobody"

    if key == "members":
        return {"name": x.get("username", ""), "detail": GL_LEVEL.get(x.get("access_level"), "")}
    if key == "protected_branches":
        return {"name": x.get("name", ""), "detail": f"push: {levels('push_access_levels')} · merge: "
                                                     f"{levels('merge_access_levels')}"
                                                     + (" · force push" if x.get("allow_force_push") else "")}
    if key == "protected_tags":
        return {"name": x.get("name", ""), "detail": f"create: {levels('create_access_levels')}"}
    if key == "hooks":
        on = [k.removesuffix("_events").replace("_", " ") for k, v in x.items() if k.endswith("_events") and v is True]
        return {"name": x.get("url", ""), "detail": ", ".join(on)}
    if key == "deploy_keys":
        return {"name": x.get("title", ""), "detail": "can push" if x.get("can_push") else "read-only"}
    if key == "variables":
        flags = [w for w, k in (("protected", "protected"), ("masked", "masked"), ("hidden", "hidden")) if x.get(k)]
        scope = x.get("environment_scope") or "*"
        return {"name": x.get("key", ""), "detail": ", ".join(flags + ([f"env {scope}"] if scope != "*" else []))}
    if key == "environments":
        return {"name": x.get("name", ""), "detail": x.get("state", "")}
    if key == "badges":
        return {"name": x.get("name") or x.get("link_url", ""), "detail": x.get("link_url", "")}
    if key == "labels":
        return {"name": x.get("name", ""), "detail": x.get("color", "")}
    return {"name": str(x.get("name") or ""), "detail": ""}


def lists_gitlab(gl, repo: str, url: str) -> list[dict]:
    proj = gl.project(repo)
    out = []
    for lst in GITLAB_LISTS:
        entry = {"key": lst.key, "label": lst.label, "manage": f"{url}/{lst.manage}" if url else "", "keep": lst.keep,
                 "note": lst.note, "items": [], "error": ""}
        try:
            entry["items"] = [item_gitlab(lst.key, x) for x in gl.pages(proj + lst.path, limit=200)]
        except core.RateLimited:
            raise
        except RuntimeError as err:
            entry["error"] = short_err(err)
        out.append(entry)
    return out


# ── checking a change ────────────────────────────────────────────────────────


def clean(provider: str, changes: dict) -> dict:
    """{key: value} of known, writable settings, each of its kind. Raises ValueError naming what's wrong."""
    if not isinstance(changes, dict) or not changes:
        raise ValueError("name the settings to change")
    out = {}
    for key, v in changes.items():
        s = find(provider, str(key))
        if s is None:
            raise ValueError(f"{key} isn't a {provider} setting")
        if s.ro:
            raise ValueError(f"{s.label} can only be read" + (f": {s.ro}" if s.ro != "facts" else ""))
        out[s.key] = coerce(s, v)
    return out


def coerce(s: Setting, v):
    if s.kind == "bool":
        if isinstance(v, str):
            low = v.strip().lower()
            if low not in ("true", "false", "on", "off", "yes", "no", "1", "0"):
                raise ValueError(f"{s.key} is on or off")
            return low in ("true", "on", "yes", "1")
        return bool(v)
    if s.kind == "int":
        try:
            n = int(v)
        except (TypeError, ValueError):
            raise ValueError(f"{s.key} is a number") from None
        if n < 0:
            raise ValueError(f"{s.key} can't be negative")
        return n
    if s.kind == "list":
        items = v.split(",") if isinstance(v, str) else list(v or [])
        return [str(x).strip() for x in items if str(x).strip()][:100]
    text = "" if v is None else str(v).strip()
    if s.kind == "choice" and text not in s.choices:
        raise ValueError(f"{s.key} is one of {', '.join(s.choices)}")
    if len(text) > 2000:
        raise ValueError(f"{s.key} is too long")
    return text


# ── writing ──────────────────────────────────────────────────────────────────


def _by_src(changes: dict, provider: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, v in changes.items():
        s = find(provider, key)
        out.setdefault(s.src, {})[s.field] = v
    return out


def _toggle(repo: str, path: str, on: bool) -> None:
    core.api("PUT" if on else "DELETE", f"/repos/{repo}{path}")


class _Attempt:
    """`with attempt(said, "what"):` runs one area's writes; a failure is said and the next area still runs."""

    def __init__(self, said: list[str], what: str):
        self.said, self.what = said, what

    def __enter__(self):
        return self

    def __exit__(self, kind, err, _tb):
        if err is None or isinstance(err, core.RateLimited) or not isinstance(err, RuntimeError):
            return False
        self.said.append(f"failed: {self.what}: {short_err(err)}")
        return True


def failed(said: list[str]) -> bool:
    return any(x.startswith("failed: ") for x in said)


def write_github(repo: str, changes: dict) -> list[str]:
    """Apply checked `changes` (see clean) through GitHub's API; one line per area written ("failed: ..." for an
    area GitHub refused: the others are still written)."""
    by = _by_src(changes, "github")
    base = f"/repos/{repo}"
    said: list[str] = []
    body = dict(by.get("main") or {})
    topics = body.pop("topics", None)
    if by.get("sec"):
        body["security_and_analysis"] = {k: {"status": "enabled" if v else "disabled"} for k, v in by["sec"].items()}
    if body:
        with _Attempt(said, "repo settings"):
            core.api("PATCH", base, body)
            said.append(f"set {', '.join(sorted(by.get('main', {}).keys() - {'topics'} | by.get('sec', {}).keys()))}")
    if topics is not None:
        with _Attempt(said, "topics"):
            core.api("PUT", f"{base}/topics", {"names": [t.lower() for t in topics]})
            said.append(f"set topics {', '.join(topics) or '(none)'}")
    if "actions" in by:
        with _Attempt(said, "Actions permissions"):
            have = core.api("GET", f"{base}/actions/permissions") or {}
            want = {"enabled": have.get("enabled", True), **by["actions"]}
            put = {"enabled": want["enabled"]}
            if want["enabled"]:
                put.update({k: want[k] for k in ("allowed_actions", "sha_pinning_required") if want.get(k) is not None})
            core.api("PUT", f"{base}/actions/permissions", put)
            said.append("set Actions permissions")
    for src in ("selected", "workflow"):
        if src in by:
            what = "the allowed actions" if src == "selected" else "the GITHUB_TOKEN permissions"
            with _Attempt(said, what):
                try:
                    have = core.api("GET", base + SOURCES[src]) or {}
                except RuntimeError:
                    have = {}
                keep = ("github_owned_allowed", "verified_allowed", "patterns_allowed") if src == "selected" else \
                    ("default_workflow_permissions", "can_approve_pull_request_reviews")
                core.api("PUT", base + SOURCES[src], {**{k: have[k] for k in keep if k in have}, **by[src]})
                said.append(f"set {what}")
    for src, what, send in (
            ("access", "Actions access", lambda d: d),
            ("retention", "artifact and log retention", lambda d: {"days": d["days"]}),
            ("forkapproval", "fork PR approval", lambda d: d)):
        if src in by:
            with _Attempt(said, what):
                core.api("PUT", base + SOURCES[src], send(by[src]))
                said.append(f"set {what} to {core.compact(next(iter(by[src].values())))}")
    for src, what in (("alerts", "Dependabot alerts"), ("autofix", "Dependabot security updates"),
                      ("pvr", "private vulnerability reporting"), ("immutable", "immutable releases")):
        if src in by:
            with _Attempt(said, what):
                on = by[src]["enabled"]
                _toggle(repo, SOURCES[src], on)
                said.append(f"turned {what} {'on' if on else 'off'}")
    if "codeql" in by:
        with _Attempt(said, "CodeQL default setup"):
            c = by["codeql"]
            patch = {}
            if "state" in c:
                patch["state"] = "configured" if c["state"] else "not-configured"
            if c.get("query_suite"):
                patch["query_suite"] = c["query_suite"]
            core.api("PATCH", base + SOURCES["codeql"], patch)
            said.append("set CodeQL default setup")
    if "pages" in by:
        with _Attempt(said, "Pages"):
            said += _write_pages(repo, by["pages"])
    if "limits" in by:
        with _Attempt(said, "interaction limit"):
            lim = by["limits"]
            limit = lim.get("limit")
            if limit is None:
                limit = (core.api("GET", base + SOURCES["limits"]) or {}).get("limit") or "none"
            if limit == "none":
                core.api("DELETE", base + SOURCES["limits"])
                said.append("removed the interaction limit")
            else:
                core.api("PUT", base + SOURCES["limits"], {"limit": limit, "expiry": lim.get("expiry") or "one_week"})
                said.append(f"limited interactions to {limit.replace('_', ' ')}")
    return said


def _write_pages(repo: str, p: dict) -> list[str]:
    path = f"/repos/{repo}/pages"
    said = []
    if p.get("on") is False:
        core.api("DELETE", path)
        return ["turned Pages off"]
    try:
        have = core.api("GET", path) or {}
    except RuntimeError as err:
        if "404" not in str(err):
            raise
        have = {}
    build = p.get("build_type") or have.get("build_type") or "workflow"
    source = {"branch": p.get("source_branch") or (have.get("source") or {}).get("branch") or "main",
              "path": p.get("source_path") or (have.get("source") or {}).get("path") or "/"}
    if not have:
        if not p.get("on"):
            raise RuntimeError("Pages is off: turn it on first")
        core.api("POST", path, {"build_type": build, **({"source": source} if build == "legacy" else {})})
        said.append("turned Pages on")
    put: dict = {}
    if "build_type" in p or (build == "legacy" and ({"source_branch", "source_path"} & p.keys())):
        put["build_type"] = build
        if build == "legacy":
            put["source"] = source
    if "cname" in p:
        put["cname"] = p["cname"] or None
    if put and (have or len(put) > 1 or "cname" in put):
        core.api("PUT", path, put)
        said.append("set Pages")
    if "https_enforced" in p:
        core.api("PUT", path, {"https_enforced": bool(p["https_enforced"])})
        said.append(f"turned Pages HTTPS {'on' if p['https_enforced'] else 'off'}")
    return said


def write_gitlab(gl, repo: str, changes: dict) -> list[str]:
    by = _by_src(changes, "gitlab")
    proj = gl.project(repo)
    said: list[str] = []
    main = dict(by.get("main") or {})
    archived = main.pop("archived", None)
    if "cleanup" in by:
        c = dict(by["cleanup"])
        if "keep_n" in c:
            c["keep_n"] = int(c["keep_n"])
        main["container_expiration_policy_attributes"] = c
    if main:
        with _Attempt(said, "project settings"):
            gl.write("PUT", proj, main)
            said.append(f"set {', '.join(sorted(main))}")
    if archived is not None:
        with _Attempt(said, "archive"):
            gl.write("POST", f"{proj}/{'archive' if archived else 'unarchive'}")
            said.append("archived it" if archived else "unarchived it")
    if "approvals" in by:
        with _Attempt(said, "approval settings"):
            gl.write("POST", f"{proj}/approvals", by["approvals"])
            said.append("set the approval settings")
    if "push" in by:
        with _Attempt(said, "push rules"):
            try:
                exists = bool(gl.api("GET", f"{proj}/push_rule"))
            except RuntimeError:
                exists = False
            gl.write("PUT" if exists else "POST", f"{proj}/push_rule", by["push"])
            said.append("set the push rules")
    if "jobtoken" in by:
        with _Attempt(said, "job token access"):
            gl.write("PATCH", f"{proj}/job_token_scope", {"enabled": by["jobtoken"]["inbound_enabled"]})
            said.append("set the job token access")
    return said


# ── keeping a change in .mason.toml ──────────────────────────────────────────


def kept(provider: str, changes: dict) -> dict[tuple, object]:
    """{.mason.toml path: value} for the changes doctor has a key for (see Setting.keep)."""
    out = {}
    for key, v in changes.items():
        s = find(provider, key)
        if not s or not s.keep:
            continue
        if s.keep.startswith("security."):
            v = "enabled" if v else "disabled"
        out[tuple(s.keep.split("."))] = v
    return out


BARE = re.compile(r"^[A-Za-z0-9_-]+$")


def tkey(k: str) -> str:
    return k if BARE.match(k) else '"' + k.replace("\\", "\\\\").replace('"', '\\"') + '"'


def tval(v) -> str:
    import json

    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(tval(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{tkey(k)} = {tval(x)}" for k, x in v.items()) + " }"
    return json.dumps(str(v))


HEADER = re.compile(r"^\s*\[\[?\s*([^\]]+?)\s*\]\]?\s*(#.*)?$")


def _drop(lines: list[str], top: str) -> list[str]:
    """`lines` without any definition of the top-level key `top`: its [top] / [top.x] tables, and before the
    first table `top = ...` or `top.x = ...` lines (a multi-line array included)."""
    out, i, in_top, skipping = [], 0, True, False
    pat = re.compile(rf"^\s*{re.escape(top)}\s*(=|\.)")
    while i < len(lines):
        line = lines[i]
        h = HEADER.match(line)
        if h:
            in_top = False
            name = h.group(1).split(".")[0].strip().strip('"')
            skipping = name == top and not line.lstrip().startswith("[[")
            if skipping:
                i += 1
                continue
        if skipping:
            i += 1
            continue
        if in_top and pat.match(line):
            depth = line.count("[") - line.count("]")
            i += 1
            while depth > 0 and i < len(lines):
                depth += lines[i].count("[") - lines[i].count("]")
                i += 1
            continue
        out.append(line)
        i += 1
    return out


def _block(name: str, table: dict) -> list[str]:
    plain = {k: v for k, v in table.items() if not isinstance(v, dict)}
    subs = {k: v for k, v in table.items() if isinstance(v, dict)}
    out = [f"[{name}]"] + [f"{tkey(k)} = {tval(v)}" for k, v in plain.items()]
    for k, v in subs.items():
        if any(isinstance(x, dict) for x in v.values()):
            out += [""] + _block(f"{name}.{tkey(k)}", v)
        else:
            out += ["", f"[{name}.{tkey(k)}]"] + [f"{tkey(a)} = {tval(b)}" for a, b in v.items()]
    if not plain and len(out) > 1 and out[1] == "":
        out = out[2:]  # only subtables: no empty [name] header needed
    return out


def keep_text(text: str, values: dict[tuple, object]) -> str:
    """`text` (a repo's .mason.toml) with each path set to its value. Other keys and comments outside the
    touched tables stay. Raises RuntimeError when the file can't be edited line by line."""
    from mason.config import parse_defaults

    data = parse_defaults(text) if text.strip() else {}
    want = _merge(data, values)
    lines = text.splitlines()
    for top in dict.fromkeys(p[0] for p in values):
        lines = _drop(lines, top)
    while lines and not lines[-1].strip():
        lines.pop()
    first = next((n for n, x in enumerate(lines) if HEADER.match(x)), len(lines))
    scalars, tables = [], []
    for top in dict.fromkeys(p[0] for p in values):
        v = want[top]
        if isinstance(v, dict):
            tables += [""] + _block(tkey(top), v)
        else:
            scalars.append(f"{tkey(top)} = {tval(v)}")
    if scalars:
        at = first
        while at > 0 and not lines[at - 1].strip():
            at -= 1
        lines[at:first] = scalars + ([""] if first < len(lines) else [])
    new = "\n".join(lines + tables).strip("\n") + "\n"
    if parse_defaults(new) != want:
        raise RuntimeError("couldn't edit .mason.toml line by line (an inline table?): "
                           "edit it in the mason files panel")
    return new


def _merge(data: dict, values: dict[tuple, object]) -> dict:
    import copy

    out = copy.deepcopy(data)
    for path, v in values.items():
        at = out
        for k in path[:-1]:
            nxt = at.get(k)
            if not isinstance(nxt, dict):
                nxt = {} if nxt is None or nxt is True else ({"enabled": False} if nxt is False else {})
                at[k] = nxt
            at = nxt
        at[path[-1]] = v
    return out


# ── the CLI ──────────────────────────────────────────────────────────────────


def show(read: dict, only: str = "", keys: bool = False) -> None:
    say = core.say
    say(f"{read['url']}")
    for area in read["areas"]:
        if only and only not in area["name"]:
            continue
        say(f"\n{area['name']}")
        for r in area["rows"]:
            v = r["value"]
            shown = "—" if v is None else ("on" if v is True else "off" if v is False else
                                           ", ".join(v) if isinstance(v, list) else str(v))
            mark = "" if r["edit"] or r["fact"] else f"   (read only: {r['why']})"
            say(f"  {r['label']:<44} {shown}{mark}" + (f"   [{r['key']}]" if keys else ""))
    for lst in read["lists"]:
        if only and only not in lst["label"]:
            continue
        say(f"\n{lst['label']} ({'?' if lst['error'] else len(lst['items'])})")
        if lst["error"]:
            say(f"  couldn't read: {lst['error']}")
        for it in lst["items"][:30]:
            say(f"  {it['name']}" + (f"  {it['detail']}" if it["detail"] else ""))
