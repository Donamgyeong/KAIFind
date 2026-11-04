"""Profile mutations use the transaction supplied by ProtectedRoute."""

from schema.profile import ProfileResponse
from service.auth import AuthService


class ProfileService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user

    def get(self):
        payload = AuthService.user_payload(self.user)
        return ProfileResponse.model_validate(payload.model_dump())

    async def update(self, body):
        self.user.language = body.language.value
        await self.db.flush()

        return self.get()
