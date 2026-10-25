/*
 * 담당: [A] | 책임: 비밀번호 규칙을 서버와 같게 화면에서 미리 검사한다.
 * PRD: 태스크 5-5-5. 계약: openapi A11 H5(영문·숫자 조합), Backend auth/password.py(8~64자, 영문·숫자 각 1개 이상).
 * 제한사항: 서버 검사를 대신하지 않는다. 서버 422도 그대로 안내한다.
 */
export const PASSWORD_RULE_TEXT = "8~64자, 영문과 숫자를 모두 포함해 주세요."

export const passwordPolicyOk = (password: string): boolean =>
  password.length >= 8 && password.length <= 64 && /[A-Za-z]/.test(password) && /\d/.test(password)

// 새 비밀번호와 확인 입력을 함께 검사한다. 문제가 없으면 null.
export const newPasswordError = (password: string, confirm: string): string | null => {
  if (!passwordPolicyOk(password)) return PASSWORD_RULE_TEXT
  if (password !== confirm) return "비밀번호 확인이 일치하지 않습니다."
  return null
}
