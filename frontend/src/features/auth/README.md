<!--
담당: [A] | 책임: 회원가입·로그인·세션 화면과 Backend 인증 연결.
구현할 기능: 계정 생성, 이메일 확인, 로그인·로그아웃, 인증 복원, 비밀번호 재설정, 탈퇴.
완료 기준: Mock/Backend 전환과 인증 상태가 화면에 반영된다.
-->
# 인증 화면과 API

## 화면

- `signup-page.tsx`: 이메일·비밀번호 회원가입
- `verify-email-page.tsx`, `resend-verification-form.tsx`: 이메일 확인과 확인 메일 재전송
- `login-page.tsx`: 로그인·로그아웃
- `forgot-password-page.tsx`, `reset-password-page.tsx`: 재설정 요청과 새 비밀번호 입력
- `account-delete-page.tsx`: 계정 탈퇴 확인

## API 연결

`auth-api.ts`가 `VITE_USE_MOCK_API`를 확인합니다. 기본 Mock 모드에서는 `src/mocks/mock-api.ts`를 사용하고, `VITE_USE_MOCK_API=false`에서는 공통 Axios로 다음 Backend 요청을 보냅니다.

| 동작 | Endpoint |
|---|---|
| 회원가입 | `POST /api/auth/signup` |
| 이메일 확인·재전송 | `POST /api/auth/email/verify`, `POST /api/auth/email/resend` |
| 로그인·Refresh·로그아웃 | `POST /api/auth/login`, `/api/auth/refresh`, `/api/auth/logout` |
| 비밀번호 재설정 | `POST /api/auth/password/reset-request`, `/api/auth/password/reset` |
| 계정 탈퇴 | `DELETE /api/account` |

Access Token은 메모리에 보관합니다. Refresh는 HttpOnly 쿠키를 사용하고 Axios 공통 계층이 CSRF와 401 Refresh 흐름을 처리합니다. `use-session-restore.ts`가 앱 세션을 복원합니다.

Backend는 `auth_service_from_env()`가 인증 서비스를 생성하면 인증 라우터를 등록합니다. 인증 화면·API 구현과 통합 검증을 완료했습니다. 실제 Backend 경로를 사용할 때에는 [`frontend/.env.development`](../../../.env.development)의 Mock 설정을 `false`로 둡니다.
