/*
 * 담당: [A] | 책임: 비밀번호 규칙을 서버와 같게 화면·Mock에서 검사한다.
 * PRD: 태스크 5-5-5. 계약: openapi A11 H5(영문·숫자 조합), Backend auth/password.py
 *   (8 <= len(password) <= 64, [A-Za-z] 1개 이상, [0-9] 1개 이상).
 * 구현: 길이는 서버(Python len)와 같이 Unicode 코드 포인트로 센다. JS string.length(UTF-16 단위)는
 *   이모지 등에서 서버와 달라 쓰지 않는다.
 * 제한사항: 서버 검사를 대신하지 않는다. 서버 422도 그대로 안내한다.
 */
import { countUnicodeCodePoints } from "./ui"

export const PASSWORD_MIN_CODE_POINTS = 8
export const PASSWORD_MAX_CODE_POINTS = 64
export const PASSWORD_RULE_TEXT = "8~64자, 영문과 숫자를 모두 포함해 주세요."

export const passwordPolicyOk = (password: string): boolean => {
  const length = countUnicodeCodePoints(password)
  return (
    length >= PASSWORD_MIN_CODE_POINTS &&
    length <= PASSWORD_MAX_CODE_POINTS &&
    /[A-Za-z]/.test(password) &&
    /[0-9]/.test(password)
  )
}

// 새 비밀번호와 확인 입력을 함께 검사한다. 문제가 없으면 null.
export const newPasswordError = (password: string, confirm: string): string | null => {
  if (!passwordPolicyOk(password)) return PASSWORD_RULE_TEXT
  if (password !== confirm) return "비밀번호 확인이 일치하지 않습니다."
  return null
}
