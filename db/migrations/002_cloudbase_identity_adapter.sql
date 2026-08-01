-- CloudBase is the identity provider. Floris retains its own stable subject,
-- membership and tenant boundary so Makers storage keys never depend on an
-- email address or a third-party provider username.
CREATE OR REPLACE FUNCTION public.bind_cloudbase_identity(
  p_candidate_user_id UUID,
  p_display_name TEXT DEFAULT '',
  p_avatar_url TEXT DEFAULT ''
)
RETURNS TABLE (
  user_id UUID,
  membership VARCHAR(16),
  roles TEXT[]
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public, pg_temp
AS $$
DECLARE
  v_tenant_id CONSTANT VARCHAR(96) := 'floris';
  v_provider_subject TEXT := NULLIF(auth.uid()::TEXT, '');
  v_candidate UUID := COALESCE(p_candidate_user_id, gen_random_uuid());
  v_user_id UUID;
  v_candidate_inserted BOOLEAN := FALSE;
  v_inserted_rows INTEGER := 0;
BEGIN
  IF v_provider_subject IS NULL THEN
    RAISE EXCEPTION 'CloudBase authentication is required'
      USING ERRCODE = '42501';
  END IF;

  -- 001 deliberately uses one tenant policy for both Neon and CloudBase.
  -- Setting it inside this trusted adapter keeps the same contract intact.
  PERFORM set_config('app.tenant_id', v_tenant_id, TRUE);

  INSERT INTO tenants (id, slug, name)
  VALUES (v_tenant_id, v_tenant_id, 'Floris')
  ON CONFLICT (id) DO NOTHING;

  SELECT identity.user_id
    INTO v_user_id
    FROM auth_identities AS identity
   WHERE identity.tenant_id = v_tenant_id
     AND identity.provider = 'cloudbase'
     AND identity.provider_subject = v_provider_subject
   FOR UPDATE;

  IF v_user_id IS NULL THEN
    INSERT INTO users (
      id, tenant_id, display_name, avatar_url, membership, roles
    ) VALUES (
      v_candidate,
      v_tenant_id,
      LEFT(COALESCE(p_display_name, ''), 120),
      LEFT(COALESCE(p_avatar_url, ''), 1000),
      'free',
      ARRAY['user']::TEXT[]
    )
    ON CONFLICT (id) DO NOTHING;
    GET DIAGNOSTICS v_inserted_rows = ROW_COUNT;
    v_candidate_inserted := v_inserted_rows = 1;

    -- The RPC is callable with a user access token, so a caller-supplied UUID
    -- is accepted only when it creates a new row. It can never claim an
    -- existing Floris user.
    IF NOT v_candidate_inserted THEN
      v_candidate := gen_random_uuid();
      INSERT INTO users (
        id, tenant_id, display_name, avatar_url, membership, roles
      ) VALUES (
        v_candidate,
        v_tenant_id,
        LEFT(COALESCE(p_display_name, ''), 120),
        LEFT(COALESCE(p_avatar_url, ''), 1000),
        'free',
        ARRAY['user']::TEXT[]
      );
      v_candidate_inserted := TRUE;
    END IF;

    INSERT INTO auth_identities (
      tenant_id, provider, provider_subject, user_id, profile_json
    ) VALUES (
      v_tenant_id,
      'cloudbase',
      v_provider_subject,
      v_candidate,
      jsonb_build_object('cloudbase_uid', v_provider_subject)
    )
    ON CONFLICT (tenant_id, provider, provider_subject) DO NOTHING;

    SELECT identity.user_id
      INTO v_user_id
      FROM auth_identities AS identity
     WHERE identity.tenant_id = v_tenant_id
       AND identity.provider = 'cloudbase'
       AND identity.provider_subject = v_provider_subject;

    IF v_candidate_inserted AND v_user_id <> v_candidate THEN
      DELETE FROM users
       WHERE id = v_candidate
         AND tenant_id = v_tenant_id
         AND NOT EXISTS (
           SELECT 1 FROM auth_identities WHERE user_id = v_candidate
         );
    END IF;
  END IF;

  UPDATE users
     SET display_name = CASE
           WHEN NULLIF(LEFT(COALESCE(p_display_name, ''), 120), '') IS NULL
             THEN display_name
           ELSE LEFT(p_display_name, 120)
         END,
         avatar_url = CASE
           WHEN NULLIF(LEFT(COALESCE(p_avatar_url, ''), 1000), '') IS NULL
             THEN avatar_url
           ELSE LEFT(p_avatar_url, 1000)
         END,
         updated_at = NOW()
   WHERE id = v_user_id AND tenant_id = v_tenant_id;

  RETURN QUERY
    SELECT account.id, account.membership, account.roles
      FROM users AS account
     WHERE account.id = v_user_id AND account.tenant_id = v_tenant_id;
END;
$$;

REVOKE ALL ON FUNCTION public.bind_cloudbase_identity(UUID, TEXT, TEXT) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.bind_cloudbase_identity(UUID, TEXT, TEXT) FROM anon;
GRANT EXECUTE ON FUNCTION public.bind_cloudbase_identity(UUID, TEXT, TEXT) TO authenticated;
