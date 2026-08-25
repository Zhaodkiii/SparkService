export interface AuthTokenWireDTO {
  user_id: number;
  access_token: string;
  refresh_token?: string;
  expires_in?: number;
  token_type: "Bearer" | string;
}

export interface CurrentSessionDTO {
  user_id: number;
  email: string;
  display_name: string;
  is_pro: boolean;
  is_new_user: boolean;
  sign_in_method: string;
  is_device_account: boolean;
}

export interface PhoneOtpRequestDTO {
  phone_number: string;
  bundle_id: string;
  device_id: string;
  scene: "login" | "account_deactivation" | "identity_bind" | "identity_change" | "identity_reauth";
}

export interface PhoneOtpRequestData {
  otp_id: string;
  expires_in: number;
}

export interface PhoneOtpVerifyDTO {
  otp_id: string;
  phone_number: string;
  code: string;
  bundle_id: string;
  device_id: string;
}

export interface AppleLoginDTO {
  identity_token: string;
  authorization_code?: string;
  nonce?: string;
  user?: string;
  email?: string;
  full_name?: string;
  bundle_id: string;
  device_id?: string;
  device_secret?: string;
}
