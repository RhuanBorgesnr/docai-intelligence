from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiExample

from ai.serializers import ChatRequestSerializer
from ai.rag import generate_answer
from documents.models import Document


@extend_schema(
    tags=['Chat'],
    summary="Chat com documentos",
    description="""
Faça perguntas sobre seus documentos usando linguagem natural.
A IA analisa o conteúdo dos documentos selecionados e responde contextualmente.

**Exemplos de perguntas:**
- "Qual a saúde financeira da empresa?"
- "Compare a margem bruta com as despesas operacionais"
- "Quais são os riscos deste contrato?"
- "Houve melhora no EBITDA?"
    """,
    request={
        'application/json': {
            'type': 'object',
            'properties': {
                'document_ids': {
                    'type': 'array',
                    'items': {'type': 'integer'},
                    'description': 'IDs dos documentos a consultar'
                },
                'question': {
                    'type': 'string',
                    'description': 'Pergunta em linguagem natural'
                }
            },
            'required': ['document_ids', 'question']
        }
    },
    examples=[
        OpenApiExample(
            'Análise financeira',
            value={
                'document_ids': [1, 2],
                'question': 'Qual a saúde financeira da empresa? Analise os principais indicadores.'
            },
            request_only=True
        ),
        OpenApiExample(
            'Comparação de períodos',
            value={
                'document_ids': [1, 2],
                'question': 'Compare a margem bruta com as despesas operacionais. A operação é sustentável?'
            },
            request_only=True
        ),
        OpenApiExample(
            'Análise de contrato',
            value={
                'document_ids': [5],
                'question': 'Quais são as cláusulas de risco neste contrato?'
            },
            request_only=True
        ),
    ],
    responses={
        200: OpenApiExample(
            'Resposta da IA',
            value={
                'answer': 'A análise dos documentos indica que a empresa apresenta alguns pontos de atenção. O prejuízo líquido foi de R$ 321.897 no período acumulado, com margem bruta negativa de -12,89%. Recomenda-se revisar a estrutura de custos...',
                'chunks_used': 5,
                'sources': [
                    {'document_id': 1, 'document_title': 'DRE 2024'}
                ]
            }
        )
    }
)
class ChatAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        document_ids = serializer.validated_data["document_ids"]
        question = serializer.validated_data["question"]

        # Enforce multi-tenant: only allow documents from user's company
        company = None
        try:
            company = request.user.userprofile.company
        except Exception:
            company = None

        allowed = Document.objects.filter(id__in=document_ids, company=company).values_list("id", flat=True)
        allowed_ids = list(allowed)

        result = generate_answer(allowed_ids, question)

        return Response(result, status=status.HTTP_200_OK)