import {
  GUEST_SKILL_IDS,
  MEMBERSHIP_PLANS,
  PAYMENT_AVAILABLE,
  PLAN_LIMITS,
} from './generated/entitlements.js';

export { MEMBERSHIP_PLANS };

const PLAN_RANK = Object.freeze({
  guest: 0,
  free: 1,
  plus: 2,
  pro: 3,
});

export function normalizeMembership(value, authType = 'guest') {
  const plan = String(value || '').toLowerCase();
  if (MEMBERSHIP_PLANS.includes(plan)) return plan;
  return authType === 'guest' ? 'guest' : 'free';
}

export function planAllows(actual, required = 'free') {
  return PLAN_RANK[normalizeMembership(actual)] >= PLAN_RANK[normalizeMembership(required, 'user')];
}

export function skillAccess(identity, skillId, requiredPlan = 'free') {
  const id = String(skillId || '');
  const authType = String(identity?.auth_type || 'guest');
  if (authType === 'guest') {
    return {
      allowed: GUEST_SKILL_IDS.includes(id),
      reason: 'login_required',
    };
  }
  if (!planAllows(identity?.membership, requiredPlan)) {
    return { allowed: false, reason: 'membership_required' };
  }
  return { allowed: true, reason: '' };
}

export function requireSkillAccess(identity, skillId, requiredPlan = 'free') {
  const access = skillAccess(identity, skillId, requiredPlan);
  if (!access.allowed) {
    const error = new Error(
      access.reason === 'login_required' ? '请先登录后使用此 Skill' : '当前会员等级无法使用此 Skill',
    );
    error.code = access.reason === 'login_required' ? 'LOGIN_REQUIRED' : 'MEMBERSHIP_REQUIRED';
    error.status = 403;
    throw error;
  }
}

export class EntitlementProvider {
  async resolve(identity) {
    const plan = normalizeMembership(identity?.membership, identity?.auth_type);
    return {
      plan,
      limits: { ...PLAN_LIMITS[plan] },
      capabilities: {
        installCommunitySkills: plan !== 'guest',
        uploadSkills: PLAN_LIMITS[plan].userSkillUploads > 0,
        paymentCheckout: PAYMENT_AVAILABLE,
      },
    };
  }
}

export class BillingProvider {
  async createCheckout() {
    throw new Error('Billing checkout is not configured');
  }

  async verifyWebhook() {
    throw new Error('Billing webhook verification is not configured');
  }

  async listTransactions() {
    return [];
  }
}

export function publicEntitlements(identity) {
  const plan = normalizeMembership(identity?.membership, identity?.auth_type);
  return {
    plan,
    limits: { ...PLAN_LIMITS[plan] },
    payment_available: PAYMENT_AVAILABLE,
  };
}
