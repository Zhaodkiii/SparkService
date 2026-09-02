"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { SparkHospitalApi } from "@/lib/api/hospital-api";
import { useAuth } from "@/context/AuthContext";
import { hospitalErrorMessage, isUnauthorizedDoctor } from "@/lib/hospital/errors";
import type { DoctorPublicDTO, HospitalPublicDTO, StaffMembershipDTO, StaffMeDTO } from "@/types/hospital";

interface DoctorAuthValue {
  me: StaffMeDTO;
  hospital: HospitalPublicDTO;
  membership: StaffMembershipDTO;
  doctor: DoctorPublicDTO;
}

const DoctorAuthContext = createContext<DoctorAuthValue | null>(null);

function UnauthorizedPage({ message, onLogout }: { message: string; onLogout: () => void }) {
  return (
    <main className="workspace doctor-state-page" role="alert">
      <div className="empty-state">
        <p className="empty-state__eyebrow">医生工作台</p>
        <h1>无法进入医生工作台</h1>
        <p>{message}</p>
        <div className="doctor-state-actions">
          <button type="button" className="doctor-button" onClick={onLogout}>退出登录</button>
        </div>
      </div>
    </main>
  );
}

export function DoctorAuthGate({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const [status, setStatus] = useState<"loading" | "ready" | "unauthorized">("loading");
  const [me, setMe] = useState<StaffMeDTO | null>(null);
  const [error, setError] = useState("当前账号没有医院医生权限，请联系医院管理员。");

  useEffect(() => {
    if (auth.status !== "authenticated") return;
    let cancelled = false;
    setStatus("loading");
    void new SparkHospitalApi(auth.client).getMe()
      .then((data) => {
        if (cancelled) return;
        if (!data.doctor || data.doctor.profile_status !== "active") {
          setError("医生身份未激活，请联系医院管理员。");
          setMe(null);
          setStatus("unauthorized");
          return;
        }
        setMe(data);
        setStatus("ready");
      })
      .catch((cause) => {
        if (cancelled) return;
        setMe(null);
        setError(isUnauthorizedDoctor(cause) ? hospitalErrorMessage(cause) : "当前账号没有医院医生权限，请联系医院管理员。");
        setStatus("unauthorized");
      });
    return () => { cancelled = true; };
  }, [auth.status, auth.client]);

  const value = useMemo<DoctorAuthValue | null>(() => {
    if (!me?.doctor) return null;
    return { me, hospital: me.hospital, membership: me.membership, doctor: me.doctor };
  }, [me]);

  if (status === "loading") {
    return <main className="workspace workspace--loading doctor-state-page" aria-busy="true"><p>正在确认医生身份…</p></main>;
  }
  if (status === "unauthorized" || !value) {
    return <UnauthorizedPage message={error} onLogout={() => void auth.logout()} />;
  }
  return <DoctorAuthContext.Provider value={value}>{children}</DoctorAuthContext.Provider>;
}

export function useDoctorAuth() {
  const value = useContext(DoctorAuthContext);
  if (!value) throw new Error("useDoctorAuth must be used inside DoctorAuthGate");
  return value;
}

export function useOptionalDoctorAuth() {
  return useContext(DoctorAuthContext);
}
