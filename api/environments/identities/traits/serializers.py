from core.constants import INTEGER
from rest_framework import exceptions, serializers

from environments.identities.models import Identity
from environments.identities.serializers import IdentitySerializer
from environments.identities.traits.fields import TraitValueField
from environments.identities.traits.models import Trait


class TraitSerializerFull(serializers.ModelSerializer):
    identity = IdentitySerializer()
    trait_value = serializers.SerializerMethodField()

    class Meta:
        model = Trait
        fields = "__all__"

    @staticmethod
    def get_trait_value(obj):
        return obj.get_trait_value()


class TraitSerializerBasic(serializers.ModelSerializer):
    trait_value = TraitValueField(allow_null=True)
    transient = serializers.BooleanField(default=False)

    class Meta:
        model = Trait
        fields = ("id", "trait_key", "trait_value", "transient")
        read_only_fields = ("id",)


class IncrementTraitValueSerializer(serializers.Serializer):
    trait_key = serializers.CharField()
    increment_by = serializers.IntegerField(write_only=True)
    identifier = serializers.CharField()
    trait_value = serializers.IntegerField(read_only=True)

    def to_representation(self, instance):
        return {
            "trait_key": instance.trait_key,
            "trait_value": instance.integer_value,
            "identifier": instance.identity.identifier,
        }

    def create(self, validated_data):
        trait, _ = Trait.objects.get_or_create(
            **self._build_query_data(validated_data),
            defaults=self._build_default_data(),
        )

        if trait.value_type != INTEGER:
            raise exceptions.ValidationError("Trait is not an integer.")

        trait.integer_value += validated_data.get("increment_by")
        trait.save()
        return trait

    def _build_query_data(self, validated_data):
        identity_data = {
            "identifier": validated_data.get("identifier"),
            "environment": self.context.get("request").environment,
        }
        identity, _ = Identity.objects.get_or_create(**identity_data)

        return {"trait_key": validated_data.get("trait_key"), "identity": identity}

    def _build_default_data(self):
        return {"value_type": INTEGER, "integer_value": 0}

    def validate(self, attrs):
        request = self.context["request"]
        if not request.environment.trait_persistence_allowed(request):
            raise serializers.ValidationError(
                "Setting traits not allowed with client key."
            )
        return attrs


class TraitKeysSerializer(serializers.Serializer):
    keys = serializers.ListSerializer(child=serializers.CharField())


class DeleteAllTraitKeysSerializer(serializers.Serializer):
    key = serializers.CharField()

    def delete(self):
        environment = self.context.get("environment")
        Trait.objects.filter(
            identity__environment=environment, trait_key=self.validated_data.get("key")
        ).delete()


class TraitSerializer(serializers.ModelSerializer):
    class Meta:
        model = Trait
        fields = (
            "id",
            "trait_key",
            "value_type",
            "integer_value",
            "string_value",
            "boolean_value",
            "float_value",
            "created_date",
        )
