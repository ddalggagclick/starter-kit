# 담당: [통합] | 책임: Supabase Session Pooler/자체 인증 ENV 연결 검증
# 구현할 기능: 5432/6543 식별, 배포 시 시크릿 및 인증 정책 검증
# 코드 경계: DB 네트워크 연결/실제 회원가입 검증은 여기서 하지 않는다.
# 완료 기준: 표준 라이브러리 테스트로 올바른/잘못된 ENV 경계 식별.
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from inheritance.core.config import Settings

BASE = {
    "APP_ENV": "test",
    "DATABASE_URL": "postgresql+asyncpg://postgres.test:pass@host.pooler.supabase.com:5432/postgres",
    "FRONTEND_ORIGIN": "http://localhost:5173",
}


class SettingsTests(unittest.TestCase):
    def load(self, **extra):
        with patch.dict(os.environ, BASE | extra, clear=True):
            return Settings.from_env()

    def test_session_pooler_passes(self):
        settings = self.load()
        self.assertEqual(settings.db_pool_size, 2)
        self.assertEqual(urlsplit(settings.database_url).port, 5432)

    def test_transaction_6543_rejected(self):
        with self.assertRaisesRegex(ValueError, "5432"):
            self.load(DATABASE_URL=BASE["DATABASE_URL"].replace(":5432", ":6543"))

    def test_production_requires_secrets(self):
        with self.assertRaises(ValueError):
            self.load(APP_ENV="production", FRONTEND_ORIGIN="https://frontend.onrender.com")

    def test_origin_must_be_exact(self):
        invalid_origins = (
            "https://frontend.onrender.com/",
            "https://user:pass@frontend.onrender.com",
            "https://frontend.onrender.com:invalid",
            "https://frontend.onrender.com?",
            " https://frontend.onrender.com",
        )
        for origin in invalid_origins:
            with self.subTest(origin=origin), self.assertRaisesRegex(ValueError, "exact origin"):
                self.load(FRONTEND_ORIGIN=origin)

    def test_invalid_database_port_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "5432"):
            self.load(DATABASE_URL="postgresql+asyncpg://localhost:invalid/postgres")

    def test_production_with_secrets_passes(self):
        c = self.load(
            APP_ENV="production",
            FRONTEND_ORIGIN="https://frontend.onrender.com",
            JWT_SIGNING_KEY="x" * 32,
            CSRF_SECRET="y" * 32,
            HANDOFF_HASH_KEY="z" * 32,
        )
        self.assertTrue(c.production)

    def test_no_automatic_fallback(self):
        with self.assertRaises(ValueError):
            self.load(LLM_AUTO_FALLBACK="true")

    def test_refresh_rotation_mandatory(self):
        with self.assertRaises(ValueError):
            self.load(REFRESH_ROTATION_ENABLED="false")

    def test_invalid_provider_rejected(self):
        with self.assertRaises(ValueError):
            self.load(LLM_PROVIDER="magical")


if __name__ == "__main__":
    unittest.main()
