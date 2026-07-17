const USERNAME_RE = /^[A-Za-z0-9._-]{3,64}$/;
export const validUsername = (value) => typeof value === 'string' && USERNAME_RE.test(value);
export const validPassword = (value) => typeof value === 'string' && value.length >= 12 && value.length <= 72;
