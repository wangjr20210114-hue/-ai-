package com.floris.android.core.model

/**
 * Normalized, read-only view of Maker's Skill entitlement response.
 *
 * The Android client deliberately does not reproduce plan, tenant, or guest
 * rules.  It only projects the fields returned by /skill_marketplace so every
 * feature surface follows the same server-owned decision.
 */
enum class SkillAccessStatus {
    Loading,
    Available,
    LoginRequired,
    Disabled,
    Unavailable,
}

data class SkillAccess(
    val skillId: String,
    val status: SkillAccessStatus,
    val reason: String? = null,
) {
    val available: Boolean get() = status == SkillAccessStatus.Available
}

data class SkillAccessProjection(
    val ready: Boolean = false,
    val refreshFailed: Boolean = false,
    val identity: Identity? = null,
    val skills: Map<String, SkillAccess> = emptyMap(),
) {
    fun access(skillId: String): SkillAccess = when {
        !ready -> SkillAccess(skillId, SkillAccessStatus.Loading)
        else -> skills[skillId]
            ?: SkillAccess(skillId, SkillAccessStatus.Unavailable, reason = "not_in_catalog")
    }

    fun withEnabled(skillId: String, enabled: Boolean): SkillAccessProjection {
        val current = skills[skillId] ?: return this
        if (current.status == SkillAccessStatus.LoginRequired ||
            current.status == SkillAccessStatus.Unavailable
        ) return this
        return copy(
            skills = skills + (
                skillId to current.copy(
                    status = if (enabled) SkillAccessStatus.Available else SkillAccessStatus.Disabled,
                )
            ),
        )
    }

    companion object {
        fun failed(previous: SkillAccessProjection): SkillAccessProjection =
            if (previous.ready) previous.copy(refreshFailed = true)
            else SkillAccessProjection(ready = true, refreshFailed = true)
    }
}

fun SkillMarketplaceState.toSkillAccessProjection(): SkillAccessProjection {
    val resolved = skills.associate { skill ->
        val enabled = skill.enabled
            ?: skill.locked?.takeIf { it }
            ?: preferences[skill.id]
            ?: true
        val eligible = skill.eligible != false
        val reason = skill.eligibility_reason
        val loginRequired = !eligible && (
            reason == "login_required" || identity?.auth_type == "guest"
        )
        val status = when {
            loginRequired -> SkillAccessStatus.LoginRequired
            !eligible -> SkillAccessStatus.Unavailable
            !enabled -> SkillAccessStatus.Disabled
            else -> SkillAccessStatus.Available
        }
        skill.id to SkillAccess(skill.id, status, reason)
    }
    return SkillAccessProjection(
        ready = true,
        identity = identity,
        skills = resolved,
    )
}
