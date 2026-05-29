"""
Transformers: DocAI extracted data → Omie API format.

Converts normalized document extraction output into the specific
payload format required by each Omie API endpoint.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from integrations.connectors.omie import OmieConnector


def _clean_cnpj_cpf(value: str) -> str:
    """Remove formatting from CNPJ/CPF, keep only digits."""
    return re.sub(r"[^\d]", "", value)


def _format_date_br(value: str | date | datetime | None) -> str:
    """Convert date to dd/mm/yyyy format required by Omie."""
    if not value:
        return date.today().strftime("%d/%m/%Y")
    if isinstance(value, (date, datetime)):
        return value.strftime("%d/%m/%Y")
    # Try to parse common formats
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    return value


def _parse_decimal(value: Any) -> float:
    """Parse value to float, handling Brazilian format (1.234,56)."""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        # Remove thousands separator and convert comma to dot
        cleaned = value.replace(".", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return 0.0
    return 0.0


class OmieTransformer:
    """Transforms DocAI extraction results into Omie API payloads."""

    @staticmethod
    def nota_fiscal_to_conta_pagar(
        extracted_data: dict[str, Any],
        connection_id: str,
        codigo_cliente_fornecedor: int | None = None,
        codigo_categoria: str = "2.01.01",
    ) -> dict[str, Any]:
        """
        Transform an extracted NF (nota fiscal) into Omie Conta a Pagar payload.
        
        Args:
            extracted_data: Output from DocAI document extraction containing:
                - numero_nf: Invoice number
                - cnpj_emitente: Issuer CNPJ
                - razao_social_emitente: Issuer name
                - data_emissao: Issue date
                - data_vencimento: Due date (or calculated from payment terms)
                - valor_total: Total value
                - descricao: Description/items
            connection_id: ERPConnection ID for idempotency
            codigo_cliente_fornecedor: Omie supplier code (if already known)
            codigo_categoria: Omie category code (default: services)
        
        Returns:
            Dict ready to send to Omie's IncluirContaPagar endpoint.
        """
        numero_nf = extracted_data.get("numero_nf", "")
        cnpj = _clean_cnpj_cpf(extracted_data.get("cnpj_emitente", ""))
        valor = _parse_decimal(extracted_data.get("valor_total", 0))
        data_vencimento = _format_date_br(extracted_data.get("data_vencimento"))
        data_emissao = _format_date_br(extracted_data.get("data_emissao"))
        descricao = extracted_data.get("descricao", "")

        # Generate deterministic integration code for idempotency
        unique_key = f"{cnpj}:{numero_nf}:{valor}"
        codigo_integracao = OmieConnector.generate_integration_code("cp", unique_key)

        payload = {
            "codigo_lancamento_integracao": codigo_integracao,
            "data_vencimento": data_vencimento,
            "valor_documento": valor,
            "codigo_categoria": codigo_categoria,
            "data_previsao": data_vencimento,
            "observacao": f"NF {numero_nf} - {descricao}"[:500],
            "numero_documento_fiscal": str(numero_nf),
            "_cnpj_emitente": cnpj,  # Internal: used for auto-resolve fornecedor
        }

        if codigo_cliente_fornecedor:
            payload["codigo_cliente_fornecedor"] = codigo_cliente_fornecedor

        return payload

    @staticmethod
    def nota_fiscal_to_conta_receber(
        extracted_data: dict[str, Any],
        connection_id: str,
        codigo_cliente_fornecedor: int | None = None,
        codigo_categoria: str = "1.01.01",
    ) -> dict[str, Any]:
        """
        Transform an extracted NF into Omie Conta a Receber payload.
        Used when DocAI's client ISSUED the invoice (receivable).
        """
        numero_nf = extracted_data.get("numero_nf", "")
        cnpj = _clean_cnpj_cpf(extracted_data.get("cnpj_destinatario", ""))
        valor = _parse_decimal(extracted_data.get("valor_total", 0))
        data_vencimento = _format_date_br(extracted_data.get("data_vencimento"))

        unique_key = f"{cnpj}:{numero_nf}:{valor}"
        codigo_integracao = OmieConnector.generate_integration_code("cr", unique_key)

        payload = {
            "codigo_lancamento_integracao": codigo_integracao,
            "data_vencimento": data_vencimento,
            "valor_documento": valor,
            "codigo_categoria": codigo_categoria,
            "data_previsao": data_vencimento,
            "observacao": f"NF {numero_nf} - Recebimento"[:500],
            "numero_documento_fiscal": str(numero_nf),
        }

        if codigo_cliente_fornecedor:
            payload["codigo_cliente_fornecedor"] = codigo_cliente_fornecedor

        return payload

    @staticmethod
    def documento_to_cliente(
        extracted_data: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Transform extracted company data into Omie Cliente payload.
        
        Args:
            extracted_data: containing:
                - cnpj_cpf: CNPJ or CPF
                - razao_social: Company name
                - nome_fantasia: Trade name (optional)
                - endereco: Address (optional)
                - cidade: City (optional)
                - estado: State UF (optional)
                - cep: ZIP code (optional)
                - telefone: Phone (optional)
                - email: Email (optional)
        """
        cnpj = _clean_cnpj_cpf(extracted_data.get("cnpj_cpf", ""))
        razao_social = extracted_data.get("razao_social", "")

        codigo_integracao = OmieConnector.generate_integration_code("cli", cnpj)

        payload = {
            "codigo_cliente_integracao": codigo_integracao,
            "cnpj_cpf": cnpj,
            "razao_social": razao_social[:60],
        }

        # Optional fields
        if nome_fantasia := extracted_data.get("nome_fantasia"):
            payload["nome_fantasia"] = nome_fantasia[:60]
        if email := extracted_data.get("email"):
            payload["email"] = email
        if telefone := extracted_data.get("telefone"):
            payload["telefone1_numero"] = re.sub(r"[^\d]", "", telefone)
        if cidade := extracted_data.get("cidade"):
            payload["cidade"] = cidade
        if estado := extracted_data.get("estado"):
            payload["estado"] = estado.upper()[:2]
        if cep := extracted_data.get("cep"):
            payload["cep"] = re.sub(r"[^\d]", "", cep)
        if endereco := extracted_data.get("endereco"):
            payload["endereco"] = endereco[:60]

        return payload

    @staticmethod
    def boleto_to_conta_pagar(
        extracted_data: dict[str, Any],
        codigo_cliente_fornecedor: int | None = None,
        codigo_categoria: str = "2.01.01",
    ) -> dict[str, Any]:
        """
        Transform extracted boleto data into Omie Conta a Pagar payload.
        
        Args:
            extracted_data: containing:
                - codigo_barras: Barcode
                - valor: Value
                - data_vencimento: Due date
                - beneficiario: Beneficiary name
                - cnpj_beneficiario: Beneficiary CNPJ
                - nosso_numero: Bank reference
        """
        valor = _parse_decimal(extracted_data.get("valor", 0))
        data_vencimento = _format_date_br(extracted_data.get("data_vencimento"))
        beneficiario = extracted_data.get("beneficiario", "")
        nosso_numero = extracted_data.get("nosso_numero", "")
        codigo_barras = extracted_data.get("codigo_barras", "")

        unique_key = f"{codigo_barras}:{valor}"
        codigo_integracao = OmieConnector.generate_integration_code("bol", unique_key)

        payload = {
            "codigo_lancamento_integracao": codigo_integracao,
            "data_vencimento": data_vencimento,
            "valor_documento": valor,
            "codigo_categoria": codigo_categoria,
            "data_previsao": data_vencimento,
            "observacao": f"Boleto - {beneficiario} - {nosso_numero}"[:500],
        }

        if codigo_cliente_fornecedor:
            payload["codigo_cliente_fornecedor"] = codigo_cliente_fornecedor

        return payload
