"""
Integration tests for ERP Integrations (Omie connector).

Tests cover:
- Models CRUD
- Transformer logic (DocAI → Omie format)
- Service layer (sync orchestration)
- API endpoints
- Idempotency
- Circuit breaker
- Approval flow
"""
from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from integrations.connectors.base import ERPResponse
from integrations.connectors.omie import OmieConnector
from integrations.models import (
    ERPConnection,
    ERPFieldMapping,
    ERPProvider,
    ERPSyncLog,
    SyncDirection,
    SyncStatus,
)
from integrations.services import (
    ERPSyncError,
    sync_cliente,
    sync_conta_pagar,
    sync_conta_receber,
    check_erp_connection,
)
from integrations.transformers.omie import OmieTransformer


# --- Fixtures ---

@pytest.fixture
def erp_connection(db):
    """Create a test ERP connection."""
    return ERPConnection.objects.create(
        provider=ERPProvider.OMIE,
        name="Test Omie Connection",
        app_key="test_app_key_123",
        app_secret="test_app_secret_456",
        is_active=True,
        requires_approval=False,
    )


@pytest.fixture
def erp_connection_with_approval(db):
    """Create a test ERP connection that requires approval."""
    return ERPConnection.objects.create(
        provider=ERPProvider.OMIE,
        name="Omie Production (Approval)",
        app_key="prod_key",
        app_secret="prod_secret",
        is_active=True,
        requires_approval=True,
    )


@pytest.fixture
def sample_nf_data():
    """Sample extracted NF data from DocAI."""
    return {
        "document_id": "doc_abc123",
        "numero_nf": "12345",
        "cnpj_emitente": "12.345.678/0001-90",
        "razao_social_emitente": "Empresa Teste Ltda",
        "data_emissao": "2026-05-15",
        "data_vencimento": "2026-06-15",
        "valor_total": "1.500,00",
        "descricao": "Serviços de consultoria em TI",
    }


@pytest.fixture
def sample_cliente_data():
    """Sample extracted client data."""
    return {
        "cnpj_cpf": "12.345.678/0001-90",
        "razao_social": "Empresa Teste Ltda",
        "nome_fantasia": "Teste Corp",
        "email": "contato@teste.com.br",
        "telefone": "(11) 99999-1234",
        "cidade": "São Paulo",
        "estado": "SP",
        "cep": "01310-100",
        "endereco": "Av Paulista 1000",
    }


@pytest.fixture
def sample_boleto_data():
    """Sample extracted boleto data."""
    return {
        "codigo_barras": "23793.38128 60000.000003 00000.000406 1 84660000015000",
        "valor": "150,00",
        "data_vencimento": "15/06/2026",
        "beneficiario": "Empresa XYZ",
        "cnpj_beneficiario": "98.765.432/0001-10",
        "nosso_numero": "123456789",
    }


@pytest.fixture
def api_client(db):
    """Authenticated API client."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.create_user(username="testuser", password="testpass123")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


# --- Model Tests ---

class TestERPConnectionModel:
    """Tests for ERPConnection model."""

    def test_create_connection(self, db):
        conn = ERPConnection.objects.create(
            provider=ERPProvider.OMIE,
            name="My Omie",
            app_key="key123",
            app_secret="secret456",
        )
        assert conn.id is not None
        assert conn.is_active is True
        assert conn.is_circuit_open is False
        assert conn.consecutive_failures == 0

    def test_record_success(self, erp_connection):
        erp_connection.consecutive_failures = 3
        erp_connection.is_circuit_open = True
        erp_connection.record_success()
        erp_connection.refresh_from_db()
        assert erp_connection.consecutive_failures == 0
        assert erp_connection.is_circuit_open is False
        assert erp_connection.last_sync_at is not None

    def test_record_failure_opens_circuit(self, erp_connection):
        for i in range(5):
            erp_connection.record_failure(f"Error {i}")
        erp_connection.refresh_from_db()
        assert erp_connection.consecutive_failures == 5
        assert erp_connection.is_circuit_open is True

    def test_record_failure_below_threshold(self, erp_connection):
        erp_connection.record_failure("Error 1")
        erp_connection.refresh_from_db()
        assert erp_connection.consecutive_failures == 1
        assert erp_connection.is_circuit_open is False


# --- Transformer Tests ---

class TestOmieTransformer:
    """Tests for DocAI → Omie data transformation."""

    def test_nf_to_conta_pagar(self, sample_nf_data):
        result = OmieTransformer.nota_fiscal_to_conta_pagar(
            sample_nf_data, connection_id="conn123"
        )
        assert result["valor_documento"] == 1500.0
        assert result["data_vencimento"] == "15/06/2026"
        assert "codigo_lancamento_integracao" in result
        assert result["numero_documento_fiscal"] == "12345"
        assert "NF 12345" in result["observacao"]

    def test_nf_to_conta_pagar_with_fornecedor(self, sample_nf_data):
        result = OmieTransformer.nota_fiscal_to_conta_pagar(
            sample_nf_data, connection_id="conn123",
            codigo_cliente_fornecedor=999,
        )
        assert result["codigo_cliente_fornecedor"] == 999

    def test_nf_to_conta_receber(self, sample_nf_data):
        sample_nf_data["cnpj_destinatario"] = "11.222.333/0001-44"
        result = OmieTransformer.nota_fiscal_to_conta_receber(
            sample_nf_data, connection_id="conn123"
        )
        assert result["valor_documento"] == 1500.0
        assert "codigo_lancamento_integracao" in result

    def test_documento_to_cliente(self, sample_cliente_data):
        result = OmieTransformer.documento_to_cliente(sample_cliente_data)
        assert result["cnpj_cpf"] == "12345678000190"
        assert result["razao_social"] == "Empresa Teste Ltda"
        assert result["nome_fantasia"] == "Teste Corp"
        assert result["email"] == "contato@teste.com.br"
        assert result["telefone1_numero"] == "11999991234"
        assert result["estado"] == "SP"
        assert result["cep"] == "01310100"
        assert "codigo_cliente_integracao" in result

    def test_boleto_to_conta_pagar(self, sample_boleto_data):
        result = OmieTransformer.boleto_to_conta_pagar(sample_boleto_data)
        assert result["valor_documento"] == 150.0
        assert result["data_vencimento"] == "15/06/2026"
        assert "Boleto" in result["observacao"]
        assert "Empresa XYZ" in result["observacao"]

    def test_idempotency_same_input_same_code(self, sample_nf_data):
        """Same input must always produce same integration code."""
        r1 = OmieTransformer.nota_fiscal_to_conta_pagar(sample_nf_data, "conn1")
        r2 = OmieTransformer.nota_fiscal_to_conta_pagar(sample_nf_data, "conn1")
        assert r1["codigo_lancamento_integracao"] == r2["codigo_lancamento_integracao"]

    def test_different_input_different_code(self, sample_nf_data):
        """Different input must produce different integration codes."""
        r1 = OmieTransformer.nota_fiscal_to_conta_pagar(sample_nf_data, "conn1")
        sample_nf_data["numero_nf"] = "99999"
        r2 = OmieTransformer.nota_fiscal_to_conta_pagar(sample_nf_data, "conn1")
        assert r1["codigo_lancamento_integracao"] != r2["codigo_lancamento_integracao"]

    def test_parse_brazilian_decimal(self):
        from integrations.transformers.omie import _parse_decimal
        assert _parse_decimal("1.500,00") == 1500.0
        assert _parse_decimal("150,50") == 150.50
        assert _parse_decimal("1000") == 1000.0
        assert _parse_decimal(250.75) == 250.75

    def test_format_date(self):
        from integrations.transformers.omie import _format_date_br
        assert _format_date_br("2026-05-15") == "15/05/2026"
        assert _format_date_br("15/06/2026") == "15/06/2026"
        assert _format_date_br(date(2026, 1, 20)) == "20/01/2026"


# --- Service Tests ---

class TestERPSyncService:
    """Tests for sync service layer."""

    @patch("integrations.services.get_connector")
    def test_sync_conta_pagar_success(self, mock_get_connector, erp_connection, sample_nf_data):
        mock_connector = MagicMock()
        mock_connector.criar_conta_pagar.return_value = ERPResponse(
            success=True,
            entity_id="12345",
            data={"codigo_lancamento_omie": 12345},
            raw_response={"codigo_lancamento_omie": 12345},
        )
        mock_get_connector.return_value = mock_connector

        result = sync_conta_pagar(
            erp_connection, sample_nf_data,
            correlation_id="test-corr-1",
            skip_approval=True,
        )

        assert result.status == SyncStatus.SUCCESS
        assert result.erp_entity_id == "12345"
        assert result.entity_type == "conta_pagar"
        assert result.correlation_id == "test-corr-1"
        assert result.duration_ms is not None

    @patch("integrations.services.get_connector")
    def test_sync_conta_pagar_failure(self, mock_get_connector, erp_connection, sample_nf_data):
        mock_connector = MagicMock()
        mock_connector.criar_conta_pagar.return_value = ERPResponse(
            success=False,
            error_code="5001",
            error_message="Cliente não encontrado",
            raw_response={"faultstring": "Cliente não encontrado"},
        )
        mock_get_connector.return_value = mock_connector

        result = sync_conta_pagar(
            erp_connection, sample_nf_data, skip_approval=True,
        )

        assert result.status == SyncStatus.FAILED
        assert "Cliente não encontrado" in result.error_message

    @patch("integrations.services.get_connector")
    def test_sync_idempotent(self, mock_get_connector, erp_connection, sample_nf_data):
        """Same document synced twice should not create duplicate."""
        mock_connector = MagicMock()
        mock_connector.criar_conta_pagar.return_value = ERPResponse(
            success=True, entity_id="100", data={}, raw_response={},
        )
        mock_get_connector.return_value = mock_connector

        r1 = sync_conta_pagar(erp_connection, sample_nf_data, skip_approval=True)
        r2 = sync_conta_pagar(erp_connection, sample_nf_data, skip_approval=True)

        # Second call returns existing log, no new API call
        assert r1.id == r2.id
        assert mock_connector.criar_conta_pagar.call_count == 1

    def test_sync_circuit_open_blocked(self, erp_connection, sample_nf_data):
        """Sync should be blocked when circuit breaker is open."""
        erp_connection.is_circuit_open = True
        erp_connection.save()

        with pytest.raises(ERPSyncError) as exc_info:
            sync_conta_pagar(erp_connection, sample_nf_data, skip_approval=True)
        assert "circuit breaker" in str(exc_info.value).lower()

    def test_sync_inactive_connection_blocked(self, erp_connection, sample_nf_data):
        """Sync should be blocked when connection is inactive."""
        erp_connection.is_active = False
        erp_connection.save()

        with pytest.raises(ERPSyncError):
            sync_conta_pagar(erp_connection, sample_nf_data, skip_approval=True)

    @patch("integrations.services.get_connector")
    def test_sync_with_approval_required(self, mock_get_connector, erp_connection_with_approval, sample_nf_data):
        """Sync with approval creates log in AWAITING_APPROVAL state."""
        result = sync_conta_pagar(
            erp_connection_with_approval, sample_nf_data,
        )
        assert result.status == SyncStatus.AWAITING_APPROVAL
        # Connector should NOT be called
        mock_get_connector.assert_not_called()

    @patch("integrations.services.get_connector")
    def test_sync_cliente(self, mock_get_connector, erp_connection, sample_cliente_data):
        mock_connector = MagicMock()
        mock_connector.criar_cliente.return_value = ERPResponse(
            success=True, entity_id="500", data={"codigo_cliente_omie": 500}, raw_response={},
        )
        mock_get_connector.return_value = mock_connector

        result = sync_cliente(erp_connection, sample_cliente_data)
        assert result.status == SyncStatus.SUCCESS
        assert result.entity_type == "cliente"

    @patch("integrations.services.get_connector")
    def test_test_connection_success(self, mock_get_connector, erp_connection):
        mock_connector = MagicMock()
        mock_connector.test_connection.return_value = ERPResponse(success=True, entity_id="ok")
        mock_get_connector.return_value = mock_connector

        result = check_erp_connection(erp_connection)
        assert result.success is True


# --- Connector Tests ---

class TestOmieConnector:
    """Tests for Omie connector (mocked HTTP)."""

    @patch("integrations.connectors.omie.OmieConnector._call")
    def test_criar_conta_pagar(self, mock_call):
        mock_call.return_value = ERPResponse(
            success=True,
            data={"codigo_lancamento_omie": 99999},
            raw_response={"codigo_lancamento_omie": 99999},
        )

        connector = OmieConnector("key", "secret")
        result = connector.criar_conta_pagar({"test": "data"})

        assert result.success is True
        assert result.entity_id == "99999"

    @patch("integrations.connectors.omie.OmieConnector._call")
    def test_pesquisar_cliente_por_cnpj(self, mock_call):
        mock_call.return_value = ERPResponse(
            success=True,
            data={"clientes_cadastro": [{"codigo_cliente_omie": 777}]},
            raw_response={},
        )

        connector = OmieConnector("key", "secret")
        result = connector.pesquisar_cliente_por_cnpj("12345678000190")

        assert result.success is True
        assert result.entity_id == "777"

    def test_generate_integration_code_deterministic(self):
        code1 = OmieConnector.generate_integration_code("cp", "data1")
        code2 = OmieConnector.generate_integration_code("cp", "data1")
        assert code1 == code2
        assert code1.startswith("cp_")

    def test_generate_integration_code_unique(self):
        code1 = OmieConnector.generate_integration_code("cp", "data1")
        code2 = OmieConnector.generate_integration_code("cp", "data2")
        assert code1 != code2


# --- API Tests ---

class TestERPIntegrationAPI:
    """Tests for DRF API endpoints."""

    def test_create_connection(self, api_client):
        response = api_client.post("/api/integrations/connections/", {
            "provider": "omie",
            "name": "Meu Omie",
            "app_key": "test_key",
            "app_secret": "test_secret",
        }, format="json")
        assert response.status_code == 201
        assert response.data["provider"] == "omie"
        assert response.data["name"] == "Meu Omie"
        assert "app_secret" not in response.data  # Secret not exposed in response

    def test_list_connections(self, api_client, erp_connection):
        response = api_client.get("/api/integrations/connections/")
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_test_connection_endpoint(self, api_client, erp_connection):
        with patch("integrations.views.check_erp_connection") as mock_test:
            mock_test.return_value = ERPResponse(success=True, entity_id="ok")
            response = api_client.post("/api/integrations/connections/test/", {
                "connection_id": str(erp_connection.id),
            }, format="json")
            assert response.status_code == 200
            assert response.data["success"] is True

    @patch("integrations.services.get_connector")
    def test_sync_document_endpoint(self, mock_get_connector, api_client, erp_connection):
        mock_connector = MagicMock()
        mock_connector.criar_conta_pagar.return_value = ERPResponse(
            success=True, entity_id="555", data={}, raw_response={},
        )
        mock_get_connector.return_value = mock_connector

        response = api_client.post("/api/integrations/sync/", {
            "connection_id": str(erp_connection.id),
            "entity_type": "conta_pagar",
            "extracted_data": {
                "numero_nf": "999",
                "cnpj_emitente": "11222333000144",
                "valor_total": "500.00",
                "data_vencimento": "2026-07-01",
            },
        }, format="json")
        assert response.status_code in (201, 202)
        assert response.data["entity_type"] == "conta_pagar"

    def test_sync_logs_endpoint(self, api_client, erp_connection):
        ERPSyncLog.objects.create(
            connection=erp_connection,
            entity_type="conta_pagar",
            direction=SyncDirection.DOCAI_TO_ERP,
            status=SyncStatus.SUCCESS,
            idempotency_key=f"test_{uuid.uuid4().hex[:8]}",
        )
        response = api_client.get("/api/integrations/sync/logs/")
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_sync_stats_endpoint(self, api_client):
        response = api_client.get("/api/integrations/sync/stats/")
        assert response.status_code == 200
        assert "connections" in response.data
        assert "last_24h" in response.data

    def test_unauthenticated_blocked(self, db):
        client = APIClient()
        response = client.get("/api/integrations/connections/")
        assert response.status_code == 401
