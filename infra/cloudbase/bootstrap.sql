-- Run only in the independent remember-me-ios environment.
CREATE SCHEMA IF NOT EXISTS remember_ios;
REVOKE ALL ON SCHEMA remember_ios FROM PUBLIC, anon, authenticated, service_role;

INSERT INTO storage.buckets (id, name, public, file_size_limit, created_at, updated_at)
VALUES ('remember-me-ios-audio', 'remember-me-ios-audio', false, 18874368, now(), now())
ON CONFLICT (id) DO NOTHING;

-- Restrictive policies prevent any broader permissive policy from exposing this bucket.
DROP POLICY IF EXISTS remember_ios_backend_only ON storage.objects;
CREATE POLICY remember_ios_backend_only ON storage.objects AS RESTRICTIVE
FOR ALL TO anon, authenticated
USING (bucket_id <> 'remember-me-ios-audio')
WITH CHECK (bucket_id <> 'remember-me-ios-audio');
