import nodemailer from 'nodemailer';
import { ENV } from '../../config/env';

export const isMailerConfigured = Boolean(ENV.SMTP_USER && ENV.SMTP_PASS);

const transporter = isMailerConfigured
  ? nodemailer.createTransport({
      host: ENV.SMTP_HOST,
      port: ENV.SMTP_PORT,
      secure: ENV.SMTP_PORT === 465,
      auth: {
        user: ENV.SMTP_USER,
        pass: ENV.SMTP_PASS,
      },
    })
  : null;

export const sendOtpEmail = async (
  to: string,
  subject: string,
  title: string,
  otpCode: string
): Promise<boolean> => {
  // Always log OTP for development testing convenience
  console.log(`[MAILER] OTP for ${to} (${title}): ${otpCode}`);

  if (!transporter) {
    console.log('[MAILER] SMTP not configured. OTP was printed to console.');
    return false;
  }

  try {
    await transporter.sendMail({
      from: `"${ENV.SMTP_FROM}" <${ENV.SMTP_USER}>`,
      to,
      subject,
      html: `
        <div style="font-family: sans-serif; padding: 20px; max-width: 500px; margin: auto; border: 1px solid #e2e8f0; border-radius: 8px;">
          <h2 style="color: #0f172a; margin-bottom: 8px;">${title}</h2>
          <p style="color: #475569; font-size: 14px;">Your verification code for CalAI is:</p>
          <div style="background-color: #f1f5f9; padding: 16px; text-align: center; border-radius: 6px; font-size: 28px; font-weight: bold; letter-spacing: 4px; color: #2563eb; margin: 16px 0;">
            ${otpCode}
          </div>
          <p style="color: #64748b; font-size: 12px;">This code will expire in 10 minutes. If you did not request this, please ignore this email.</p>
        </div>
      `,
    });
    return true;
  } catch (error) {
    console.error('[MAILER] Failed to send email via SMTP:', error);
    return false;
  }
};
