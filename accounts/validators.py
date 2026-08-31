from django.core.exceptions import ValidationError

MAX_PASSWORD_LENGTH = 60


class MaximumLengthValidator:
    """Django ships MinimumLengthValidator but no maximum, so nothing capped
    password length. Registered in AUTH_PASSWORD_VALIDATORS rather than added to
    each serializer: register/change/reset all already call validate_password().

    ponytail: not applied at login -- an existing account with a longer password
    must still be able to sign in and change it.
    """

    def __init__(self, max_length=MAX_PASSWORD_LENGTH):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                'Password must be at most %(max_length)d characters long.',
                code='password_too_long',
                params={'max_length': self.max_length},
            )

    def get_help_text(self):
        return f'Your password must be at most {self.max_length} characters.'
