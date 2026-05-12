from rest_framework import serializers
from timezone_field.rest_framework import TimeZoneSerializerField
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from datetime import timedelta
from django.core.mail import send_mail
from django.conf import settings
from rest_framework_simplejwt.tokens import AccessToken
from jwt import InvalidTokenError
import re
from rest_framework.serializers import ValidationError
from .models import User, PasswordReset, Role


class UserRegistrationSerializer(serializers.ModelSerializer):
    """
    Serializer for user registration
    """
    password = serializers.CharField(write_only=True, validators=[validate_password])
    password_confirm = serializers.CharField(write_only=True)
    role = serializers.SlugRelatedField(slug_field='name', queryset=Role.objects.all())
    
    class Meta:
        model = User
        fields = ('email', 'username', 'role', 'password', 'password_confirm', 'first_name', 'last_name')
        extra_kwargs = {
            'email': {'required': True},
            'username': {'required': False},
            'role': {'required': True},
            'first_name': {'required': True},
            'last_name': {'required': False},
            'password': {'write_only': True},
            'password_confirm': {'write_only': True},
        }
    
    def validate_email(self, value):
        # Custom validation as per requirements:
        # 1. Must contain @
        # 2. Domain part (after @) must be > 2 characters before the dot
        # 3. Must have a dot
        # 4. Characters after dot must be >= 2
        
        # Regex explanation:
        # ^[^@]+        : Start with at least one non-@ character
        # @             : Mandatory @ symbol
        # [^@.]{3,}     : At least 3 characters (more than 2) that are not @ or dot
        # \.            : Mandatory dot
        # [^@]{2,}$     : At least 2 characters at the end
        if not re.match(r'^[^@]+@[^@.]{3,}\.[^@]{2,}$', value):
             raise serializers.ValidationError('Invalid email format. Domain must be more than 2 characters and extension must be at least 2 characters (e.g., example@domain.com).')

        if User.objects.filter(email=value).exists():
             raise serializers.ValidationError('A user with this email already exists.')
        return value

    def validate_username(self, value):
        if value:
            if not re.match(r'^[a-zA-Z0-9]+$', value):
                raise ValidationError('Username can only contain alphanumeric characters.')
            if User.objects.filter(username=value).exists():
                raise serializers.ValidationError('A user with this username already exists.')
        return value
    
    def validate_first_name(self, value):
        if not re.match(r'^[a-zA-Z\s]+$', value):
            raise ValidationError('First name can only contain alphabets and spaces.')
        return value
    
    def validate_last_name(self, value):
        if value and not re.match(r'^[a-zA-Z\s]+$', value):
            raise ValidationError('Last name can only contain alphabets and spaces.')
        return value
    
    def validate(self, attrs):
        password = attrs['password']
        password_confirm = attrs['password_confirm']
        
        if password != password_confirm:
            raise ValidationError("Passwords don't match.")
        
        if len(password) < 8:
            raise ValidationError({'password': 'Password must be at least 8 characters long.'})
        
        if not re.match(r'^.+$', password):
            raise ValidationError({'password': 'Invalid password format.'})
        
        validate_password(password)
        
        return attrs
    
    def create(self, validated_data):
        validated_data.pop('password_confirm')
        
        # Auto-generate username if not provided
        if 'username' not in validated_data or not validated_data['username']:
            email = validated_data.get('email')
            base_username = email.split('@')[0]
            # Sanitize username to be alphanumeric
            base_username = re.sub(r'[^a-zA-Z0-9]', '', base_username)
            if not base_username:
                base_username = 'user'
                
            username = base_username
            counter = 1
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            validated_data['username'] = username

        # Role can be provided as id or name via nested representation
        role_value = validated_data.pop('role', None)
        role_obj = None
        if isinstance(role_value, Role):
            role_obj = role_value
        elif isinstance(role_value, dict):
            role_id = role_value.get('id')
            role_name = role_value.get('name')
            if role_id:
                role_obj = Role.objects.get(id=role_id)
            elif role_name:
                role_obj, _ = Role.objects.get_or_create(name=str(role_name).lower())
        elif role_value is not None:
            # If a primitive is passed, try interpret as id else as name
            try:
                role_obj = Role.objects.get(id=int(role_value))
            except Exception:
                role_obj, _ = Role.objects.get_or_create(name=str(role_value).lower())

        user = User.objects.create_user(**validated_data, role=role_obj)

        # Create related profile based on role using safe defaults
        user_role = (user.role.name if user.role_id else None)
        try:
            if user_role == getattr(settings, 'USER_ROLE_CANDIDATE', 'candidate'):
                # Lazy import to avoid circular deps at import time
                from candidates.models import Candidate
                full_name = f"{user.first_name} {user.last_name}".strip() or user.get_short_name()
                # Title is required at model level (blank not allowed). Use a safe default.
                Candidate.objects.get_or_create(
                    user=user,
                    defaults={
                        'full_name': full_name or user.email.split('@')[0],
                        'title': 'Candidate',
                    }
                )
            elif user_role == getattr(settings, 'USER_ROLE_EMPLOYER', 'employer'):
                from employers.models import Employer
                Employer.objects.get_or_create(
                    user=user,
                    defaults={
                        'first_name': user.first_name or user.get_short_name(),
                        'last_name': user.last_name or '',
                    }
                )
        except Exception:
            # Do not block user creation if profile creation fails
            pass

        # Send verification email
        try:
             token = AccessToken.for_user(user)
             token['purpose'] = 'email_verification'
             # Set a reasonable expiration for verification link (e.g. 24 hours) if possible, 
             # but AccessToken default lifetime is often short. 
             # For verification, we might want a longer lifetime or a separate token type.
             token.set_exp(lifetime=timedelta(minutes=15))
             
             verification_url = f"{getattr(settings, 'FLIT_REQUEST_URL')}/auth/verify-email?token={token}"
             
             from utils.email_service import send_verification_email
             send_verification_email(user, verification_url)
        except Exception as e:
            # Log error but don't fail registration
             # import logging
             # logger = logging.getLogger(__name__)
             # logger.error(f"Failed to send verification email to {user.email}: {e}")
             pass

        return user


class UserLoginSerializer(serializers.Serializer):
    """
    Serializer for user login
    """
    email = serializers.EmailField()
    password = serializers.CharField()
    
    def validate(self, attrs):
        email = attrs.get('email')
        password = attrs.get('password')
        
        if email and password:
            user = authenticate(username=email, password=password)
            if not user:
                raise serializers.ValidationError('Invalid credentials.')
            if not user.is_active:
                raise serializers.ValidationError('User account is disabled.')
            
            if not getattr(user, 'is_verified', False):
                 raise serializers.ValidationError('Please verify your email address before logging in.')
            attrs['user'] = user
        else:
            raise serializers.ValidationError('Must include email and password.')
        
        return attrs


class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for user profile
    """
    full_name = serializers.ReadOnlyField()
    # If the user has an employer profile, expose the related company id and name
    company = serializers.IntegerField(source='employer_profile.company.id', read_only=True, allow_null=True)
    company_name = serializers.CharField(source='employer_profile.company.company_name', read_only=True, allow_null=True)
    
    role = serializers.CharField(source='role.name', read_only=True, allow_null=True)
    role_id = serializers.IntegerField(source='role.id', read_only=True, allow_null=True)
    user_timezone = TimeZoneSerializerField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'role', 'role_id', 'first_name', 'last_name', 'full_name',
            'created_at', 'company', 'company_name', 'is_verified', 'user_timezone'
        )
        read_only_fields = ('id', 'email', 'role', 'role_id', 'created_at')
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        # Hide employer-specific fields for non-employer roles (e.g., candidates)
        role_name = getattr(getattr(instance, 'role', None), 'name', None)
        employer_role = getattr(settings, 'USER_ROLE_EMPLOYER', 'employer')
        if role_name != employer_role:
            data.pop('company', None)
            data.pop('company_name', None)
        return data


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating user profile
    """
    user_timezone = TimeZoneSerializerField(required=False)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'username', 'user_timezone')

    def update(self, instance, validated_data):
        # Update fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)

        # Check profile completeness
        required_fields = ['first_name', 'last_name', 'username']
        if all(getattr(instance, field) for field in required_fields):
            instance.profile_completed = True

        instance.save()
        return instance


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for changing password
    """
    old_password = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()
    
    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match.")

        password = attrs['new_password']
        
        if len(password) < 8:
            raise ValidationError({'new_password': 'Password must be at least 8 characters long.'})
        
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$', password):
            raise ValidationError({'new_password': 'Password must contain at least one uppercase letter, one lowercase letter, one digit, and at least one special character.'})
        
        validate_password(password)
        
        return attrs
    
    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value


class UserListSerializer(serializers.ModelSerializer):
    """
    Serializer for listing users (admin view)
    """
    full_name = serializers.ReadOnlyField()
    
    role = serializers.CharField(source='role.name', read_only=True, allow_null=True)

    class Meta:
        model = User
        fields = ('id', 'email', 'username', 'role', 'full_name', 
                 'profile_completed', 'created_at')


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('No user found with this email.')
        self.context['user'] = user
        return value

    def create(self, validated_data):
        user = self.context['user']
        # Generate short-lived JWT token specifically for password reset
        reset_token = AccessToken.for_user(user)
        reset_token['purpose'] = 'password_reset'
        reset_token.set_exp(lifetime=timedelta(minutes=10))
        token_str = str(reset_token)
        expires_at = timezone.now() + timedelta(minutes=10)

        # Store record
        PasswordReset.objects.create(
            user=user,
            email=user.email,
            reset_token=token_str,
            expires_at=expires_at,
        )

        reset_url = f"{settings.PASSWORD_RESET_URL}?token={token_str}"
        
        from utils.email_service import send_password_reset_email
        send_password_reset_email(user, reset_url)

        return {
            'email': user.email,
            'expires_at': expires_at,
        }


class PasswordResetConfirmSerializer(serializers.Serializer):
    reset_token = serializers.CharField()
    new_password = serializers.CharField(validators=[validate_password])
    new_password_confirm = serializers.CharField()

    def validate(self, attrs):
        if attrs['new_password'] != attrs['new_password_confirm']:
            raise serializers.ValidationError("New passwords don't match.")

        password = attrs['new_password']
        
        if len(password) < 8:
            raise ValidationError({'new_password': 'Password must be at least 8 characters long.'})
        
        if not re.match(r'^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[^\w\s]).+$', password):
            raise ValidationError({'new_password': 'Password must contain at least one uppercase letter, one lowercase letter, one digit, and at least one special character.'})
        
        validate_password(password)

        token_str = attrs['reset_token']

        # Verify JWT token
        try:
            access = AccessToken(token_str)
        except Exception:
            raise serializers.ValidationError('Invalid or malformed reset token.')

        # Ensure token purpose
        if access.payload.get('purpose') != 'password_reset':
            raise serializers.ValidationError('Invalid reset token purpose.')

        user_id = access.payload.get('user_id')
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise serializers.ValidationError('Invalid reset token.')

        try:
            reset = PasswordReset.objects.filter(
                user=user,
                reset_token=token_str,
            ).latest('created_at')
        except PasswordReset.DoesNotExist:
            raise serializers.ValidationError('Invalid or expired reset token.')

        if reset.used_at is not None:
            raise serializers.ValidationError('This reset token has already been used.')
        if reset.is_expired:
            raise serializers.ValidationError('The token has expired. Please request a new reset.')

        self.context['user'] = user
        self.context['reset'] = reset
        return attrs

    def save(self, **kwargs):
        user = self.context['user']
        reset = self.context['reset']
        user.set_password(self.validated_data['new_password'])
        user.save(update_fields=['password'])
        reset.mark_used()
        return user


class ResendVerificationEmailSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError('No user found with this email.')
        
        if user.is_verified:
            raise serializers.ValidationError('This email is already verified.')
            
        self.context['user'] = user
        return value

    def save(self):
        user = self.context['user']
        token = AccessToken.for_user(user)
        token['purpose'] = 'email_verification'
        token.set_exp(lifetime=timedelta(minutes=15))
        
        verification_url = f"{getattr(settings, 'FLIT_REQUEST_URL')}/auth/verify-email?token={token}"
        
        from utils.email_service import send_verification_email
        return send_verification_email(user, verification_url)