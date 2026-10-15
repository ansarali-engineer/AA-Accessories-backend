from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import serializers

from accounts.models import Customer

User = get_user_model()


class UserSummarySerializer(serializers.ModelSerializer):
    is_staff = serializers.BooleanField(read_only=True)

    class Meta:
        model = User
        fields = ("id", "username", "email", "first_name", "last_name", "is_staff")


class CustomerSerializer(serializers.ModelSerializer):
    user = UserSummarySerializer(read_only=True)
    username = serializers.CharField(write_only=True)
    email = serializers.EmailField(write_only=True)
    first_name = serializers.CharField(write_only=True, required=False, allow_blank=True)
    last_name = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = Customer
        fields = (
            "id",
            "user",
            "username",
            "email",
            "first_name",
            "last_name",
            "phone",
            "city",
            "tier",
            "created_at",
        )
        read_only_fields = ("id", "created_at")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def create(self, validated_data):
        user_data = {
            "username": validated_data.pop("username"),
            "email": validated_data.pop("email"),
            "first_name": validated_data.pop("first_name", ""),
            "last_name": validated_data.pop("last_name", ""),
        }
        user = User.objects.create_user(**user_data)
        return Customer.objects.create(user=user, **validated_data)


class CustomerRegistrationSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True, min_length=8, trim_whitespace=False)
    first_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    last_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    city = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("A user with this username already exists.")
        return value

    def validate(self, attrs):
        user = User(username=attrs["username"], email=attrs["email"])
        try:
            validate_password(attrs["password"], user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"password": list(exc.messages)}) from exc
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        password = validated_data.pop("password")
        user_data = {
            key: validated_data.pop(key)
            for key in ("username", "email", "first_name", "last_name")
        }
        user = User.objects.create_user(password=password, **user_data)
        return Customer.objects.create(user=user, **validated_data)
