import React, { useState, useEffect } from 'react';
import api from '../services/api';

export default function Settings() {
  const [profile, setProfile] = useState({
    phone: '',
    notification_preference: 'email',
    notify_expiration_days: 7,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadProfile();
    // Timeout de segurança - não ficar travado no loading
    const timeout = setTimeout(() => setLoading(false), 3000);
    return () => clearTimeout(timeout);
  }, []);

  const loadProfile = async () => {
    try {
      const res = await api.get('/accounts/profile/');
      setProfile(res.data);
    } catch (err) {
      console.error('Erro ao carregar perfil:', err);
      // Continua com valores padrão
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    setMessage(null);

    try {
      await api.patch('/accounts/profile/', profile);
      setMessage({ type: 'success', text: 'Configurações salvas com sucesso!' });
    } catch (err) {
      console.error('Erro ao salvar:', err);
      setMessage({ type: 'error', text: 'Erro ao salvar configurações.' });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field, value) => {
    setProfile((prev) => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Configurações</h1>
        <div className="flex justify-center items-center h-32">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Configurações</h1>

      {message && (
        <div
          className={`mb-4 p-4 rounded-lg ${
            message.type === 'success'
              ? 'bg-green-50 text-green-800 border border-green-200'
              : 'bg-red-50 text-red-800 border border-red-200'
          }`}
        >
          {message.text}
        </div>
      )}

      <form onSubmit={handleSubmit} className="bg-white shadow rounded-lg p-6 space-y-6">
        <div>
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Preferências de Notificação
          </h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Telefone (WhatsApp)
              </label>
              <input
                type="tel"
                value={profile.phone || ''}
                onChange={(e) => handleChange('phone', e.target.value)}
                placeholder="(11) 99999-9999"
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
              <p className="mt-1 text-sm text-gray-500">
                Inclua o DDD. Ex: 11999999999
              </p>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Receber notificações por
              </label>
              <select
                value={profile.notification_preference}
                onChange={(e) => handleChange('notification_preference', e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="email">Apenas Email</option>
                <option value="whatsapp">Apenas WhatsApp</option>
                <option value="both">Email e WhatsApp</option>
                <option value="none">Nenhum</option>
              </select>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Dias de antecedência para alertas
              </label>
              <select
                value={profile.notify_expiration_days}
                onChange={(e) => handleChange('notify_expiration_days', parseInt(e.target.value))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value={3}>3 dias</option>
                <option value={5}>5 dias</option>
                <option value={7}>7 dias</option>
                <option value={14}>14 dias</option>
                <option value={30}>30 dias</option>
              </select>
              <p className="mt-1 text-sm text-gray-500">
                Você será notificado quando documentos estiverem próximos do vencimento.
              </p>
            </div>
          </div>
        </div>

        <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
          <h3 className="text-sm font-medium text-blue-800 mb-2">
            Sobre as notificações
          </h3>
          <ul className="text-sm text-blue-700 space-y-1">
            <li>• Alertas de vencimento são enviados diariamente às 8h</li>
            <li>• WhatsApp requer número válido com DDD</li>
            <li>• Você pode cancelar a qualquer momento</li>
          </ul>
        </div>

        <div className="flex justify-end">
          <button
            type="submit"
            disabled={saving}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {saving ? 'Salvando...' : 'Salvar Configurações'}
          </button>
        </div>
      </form>
    </div>
  );
}
