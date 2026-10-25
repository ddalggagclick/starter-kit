// 비밀번호 규칙 테스트(5-5-5): 서버(Python len = 코드 포인트)와 같은 길이 계산인지 확인한다.
import { describe, expect, it } from "vitest"
import { newPasswordError, passwordPolicyOk } from "./password-policy"

const emoji = "😀" // JS length 2, 코드 포인트 1

describe("passwordPolicyOk", () => {
  it("영문·숫자를 모두 포함한 8~64자를 허용한다", () => {
    expect(passwordPolicyOk("mockpass1")).toBe(true)
    expect(passwordPolicyOk("onlyletters")).toBe(false)
    expect(passwordPolicyOk("12345678")).toBe(false)
  })

  it("이모지는 서버처럼 1글자로 센다: 코드 포인트 64자는 허용(JS length 126)", () => {
    const password = `a1${emoji.repeat(62)}`
    expect(password.length).toBe(126)
    expect(passwordPolicyOk(password)).toBe(true)
  })

  it("코드 포인트 65자는 거부한다", () => {
    expect(passwordPolicyOk(`a1${emoji.repeat(63)}`)).toBe(false)
  })

  it("코드 포인트 7자는 JS length가 8 이상이어도 거부한다", () => {
    const password = `a1${emoji.repeat(5)}`
    expect(password.length).toBe(12)
    expect(passwordPolicyOk(password)).toBe(false)
  })

  it("영문·숫자 판정은 서버와 같이 ASCII만 인정한다", () => {
    expect(passwordPolicyOk("가나다라마바사1")).toBe(false)
    expect(passwordPolicyOk("abcdefg١")).toBe(false) // 아랍 숫자
  })
})

describe("newPasswordError", () => {
  it("규칙 위반과 확인 불일치를 구분한다", () => {
    expect(newPasswordError("short1", "short1")).toMatch(/8~64자/)
    expect(newPasswordError("newpass123", "newpass124")).toBe("비밀번호 확인이 일치하지 않습니다.")
    expect(newPasswordError("newpass123", "newpass123")).toBeNull()
  })
})
