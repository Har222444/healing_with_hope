import React from "react";

interface PageWrapperProps {
  children: React.ReactNode;
}

const PageWrapper: React.FC<PageWrapperProps> = ({ children }) => {
  return (
    <div className="min-h-screen w-full pb-24 lg:pb-0 lg:pl-32 transition-all duration-500">
      {children}
    </div>
  );
};

export default PageWrapper;
