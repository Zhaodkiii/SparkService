import type { SparkHttpClient } from "@/lib/api/http-client";
import type {
  AppleLoginDTO,
  AuthTokenWireDTO,
  CurrentSessionDTO,
  PhoneOtpRequestDTO,
  PhoneOtpRequestData,
  PhoneOtpVerifyDTO,
} from "@/types/auth";

export class SparkAuthApi {
  constructor(private readonly http: SparkHttpClient) {}

  requestPhoneOtp(payload: PhoneOtpRequestDTO, requestId?: string): Promise<PhoneOtpRequestData> {
    return this.http.requestOrThrow("POST", "/api/auth/phone/request", { body: payload, requestId });
  }

  verifyPhoneOtp(payload: PhoneOtpVerifyDTO, requestId?: string): Promise<AuthTokenWireDTO> {
    return this.http.requestOrThrow("POST", "/api/auth/phone/verify", { body: payload, requestId });
  }

  loginWithApple(payload: AppleLoginDTO): Promise<AuthTokenWireDTO> {
    return this.http.requestOrThrow("POST", "/api/auth/apple/callback", { body: payload });
  }

  bootstrap(deviceId?: string, requestId?: string): Promise<AuthTokenWireDTO & { session?: CurrentSessionDTO }> {
    return this.http.requestOrThrow("POST", "/api/auth/bootstrap", {
      headers: deviceId ? { "X-Device-ID": deviceId } : undefined,
      requestId,
    });
  }

  currentSession(): Promise<CurrentSessionDTO> {
    return this.http.requestOrThrow("GET", "/api/auth/session");
  }

  logout(): Promise<Record<string, never>> {
    return this.http.requestOrThrow("POST", "/api/auth/logout");
  }
}
