from rest_framework.response import Response


def success_response(data=None, msg: str = "success", code: int = 0, status_code: int = 200):
    return Response({"code": code, "msg": msg, "data": data}, status=status_code)


def error_response(msg="error", code: int = -1, status_code: int = 400, data=None):
    return Response({"code": code, "msg": msg, "data": data}, status=status_code)

