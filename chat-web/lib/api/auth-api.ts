import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  AppleLoginDTO,
  AuthTokenWireDTO,
  CurrentSessionDTO,
  PhoneOtpRequestData,
  WebPhoneOtpRequestDTO,
  WebPhoneOtpVerifyDTO,
} from "@/types/auth";

export class SparkAuthApi {
  constructor(private readonly http: SparkHttpClient) {}

  requestPhoneOtp(payload: WebPhoneOtpRequestDTO, requestId?: string): Promise<PhoneOtpRequestData> {
    return this.http.requestOrThrow("POST", "/api/auth/phone/request", { body: payload, requestId });
  }

  verifyPhoneOtp(payload: WebPhoneOtpVerifyDTO, requestId?: string): Promise<AuthTokenWireDTO> {
    return this.http.requestOrThrow("POST", "/api/auth/phone/verify", { body: payload, requestId });
  }

  loginWithApple(payload: AppleLoginDTO): Promise<AuthTokenWireDTO> {
    return this.http.requestOrThrow("POST", "/api/auth/apple/callback", { body: payload });
  }

  /** 019E：Web Session 恢复不再提交移动 device_id；上游按 refresh token 内的 web_session_id 分派。 */
  bootstrap(requestId?: string): Promise<AuthTokenWireDTO & { session?: CurrentSessionDTO }> {
    return this.http.requestOrThrow("POST", "/api/auth/bootstrap", { requestId });
  }

  currentSession(): Promise<CurrentSessionDTO> {
    return this.http.requestOrThrow("GET", "/api/auth/session");
  }

  logout(): Promise<Record<string, never>> {
    return this.http.requestOrThrow("POST", "/api/auth/logout");
  }
}
