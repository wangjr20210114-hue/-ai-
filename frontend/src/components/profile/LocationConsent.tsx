import { useEffect, useState } from 'react';
import { Dialog, MessagePlugin } from 'tdesign-react';
import { readLocationConsent, requestCurrentLocation, setLocationConsent } from '../../services/location';

export default function LocationConsent() {
  const [visible, setVisible] = useState(false);
  const [locating, setLocating] = useState(false);

  useEffect(() => {
    setVisible(readLocationConsent() === 'unknown');
  }, []);

  const allow = async () => {
    setLocating(true);
    try {
      await requestCurrentLocation();
      setVisible(false);
      MessagePlugin.success('已获取当前位置；精确坐标只保留在本次浏览器会话中');
    } catch (error) {
      setLocationConsent('denied');
      setVisible(false);
      MessagePlugin.warning(error instanceof Error ? error.message : '定位未授权');
    } finally {
      setLocating(false);
    }
  };

  return (
    <Dialog
      visible={visible}
      header="是否提供当前位置？"
      confirmBtn={{ content: '允许本次定位', loading: locating }}
      cancelBtn="暂不提供"
      onConfirm={() => { void allow(); }}
      onCancel={() => {
        setLocationConsent('denied');
        setVisible(false);
      }}
      onClose={() => {
        setLocationConsent('denied');
        setVisible(false);
      }}
    >
      当今天没有可连接的日程路线时，地图会显示你的位置。坐标不会写入长期记忆或上传为用户画像。
    </Dialog>
  );
}
