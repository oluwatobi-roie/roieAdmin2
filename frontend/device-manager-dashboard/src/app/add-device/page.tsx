'use client';

import { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { toast } from 'sonner';

export default function AddDevicePage() {
  const { auth_loading, authenticated } = useAuth();
  const [mode, setMode] = useState<'single' | 'bulk'>('single');
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    uniqueid: '',
    count: ''
  });
  const [loading, setLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  const handleChange = (e: any) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    setFeedback(null);

    if (!formData.name || (mode === 'single' && (!formData.phone || !formData.uniqueid))) {
      setFeedback({ type: 'error', message: 'Please fill in all required fields' });
      return;
    }

    if (mode === 'bulk' && (Number(formData.count) < 1 || Number(formData.count) > 15)) {
      setFeedback({ type: 'error', message: 'Count must be between 1 and 15' });
      return;
    }

    setLoading(true);

    const payload = {
      mode,
      ...(mode === 'bulk'
        ? { name: formData.name, count: Number(formData.count) }
        : { name: formData.name, phone: formData.phone, uniqueid: formData.uniqueid }
      )
    };

    try {
      const res = await fetch('/api/device/add_device', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();

      if (res.ok) {
        setFeedback({ type: 'success', message: 'Device(s) added successfully!' });
        toast.success('Device(s) added successfully!');
        setFormData({ name: '', phone: '', uniqueid: '', count: '' });
      } else {
        setFeedback({ type: 'error', message: data.error || 'Failed to add device' });
        toast.error(data.error || 'Failed to add device');
      }
    } catch (err) {
      console.error(err);
      setFeedback({ type: 'error', message: 'Server error occurred' });
      toast.error('Server error occurred');
    } finally {
      setLoading(false);
    }
  };

  // ---------- CONDITIONAL RENDER ----------
  if (auth_loading) return <p className="text-center py-10">Checking You have access... please wait</p>;
  if (!authenticated) return null;

  return (
    <main className="min-h-screen bg-gray-50 px-4 py-8 sm:px-6 md:px-12">
      <div className="max-w-xl mx-auto space-y-6">
        <h1 className="text-2xl sm:text-3xl font-bold text-[#414095]">
            ➕ Add Device
        </h1>
        <p className="text-[#428fda] text-sm sm:text-base">
            Switch between bulk and single device mode
        </p>
        

        {/* Feedback message */}
        {feedback && (
          <p
            className={`text-center py-2 px-4 rounded-md ${
              feedback.type === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
            }`}
          >
            {feedback.message}
          </p>
        )}

        {/* Mode Toggle */}
        <ToggleGroup
          type="single"
          value={mode}
          onValueChange={(val: any) => val && setMode(val)}
          className="w-full justify-center mb-4"
        >
          <ToggleGroupItem value="single">Single</ToggleGroupItem>
          <ToggleGroupItem value="bulk">Bulk</ToggleGroupItem>
        </ToggleGroup>

        {/* Form Card */}
        <Card className="shadow-lg border border-[#428fda] hover:shadow-2xl transition-shadow bg-gradient-to-r from-[#e2e4f7] to-[#d6ebfa] rounded-xl">
          <CardContent className="p-6 space-y-4">
            <Input
              name="name"
              placeholder="Device Name"
              value={formData.name}
              onChange={handleChange}
              className="border-[#428fda] focus:ring-[#414095]"
            />

            {mode === 'single' ? (
              <>
                <Input
                  name="phone"
                  placeholder="Phone"
                  value={formData.phone}
                  onChange={handleChange}
                  className="border-[#428fda] focus:ring-[#414095]"
                />
                <Input
                  name="uniqueid"
                  placeholder="Unique ID / IMEI"
                  value={formData.uniqueid}
                  onChange={handleChange}
                  className="border-[#428fda] focus:ring-[#414095]"
                />
              </>
            ) : (
              <Input
                name="count"
                type="number"
                placeholder="Count (max 15)"
                value={formData.count}
                onChange={handleChange}
                min={1}
                max={15}
                className="border-[#428fda] focus:ring-[#414095]"
              />
            )}

            <Button
              onClick={handleSubmit}
              className="w-full bg-[#428fda] hover:bg-[#414095] text-white"
              disabled={loading || (mode === 'bulk' && (Number(formData.count) < 1 || Number(formData.count) > 15))}
            >
              {loading ? 'Submitting...' : 'Submit'}
            </Button>
          </CardContent>
        </Card>
      </div>
    </main>
  );
}
